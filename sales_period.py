"""Calendar periods and native Streamlit selectors; no database writes."""
from display_preferences import tr
from typing import Literal, overload
import calendar
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

MODES = ('Day', 'Week', 'Month', 'Custom')
STATE_KEY = 'bizmar_sales_period'


def period_bounds(mode, selected):
    if mode == 'Day':
        return selected, selected
    if mode == 'Week':
        start = selected - timedelta(days=selected.weekday())
        return start, start + timedelta(days=6)
    if mode == 'Month':
        return selected.replace(day=1), selected.replace(day=calendar.monthrange(selected.year, selected.month)[1])
    raise ValueError('Custom periods require explicit start and end dates.')


def utc_bounds(start, end):
    """Inclusive MYT calendar dates as a half-open UTC timestamp interval."""
    if end < start:
        raise ValueError('End date must be on or after start date.')
    return (pd.Timestamp(start).tz_localize('Asia/Kuala_Lumpur').tz_convert('UTC'),
            pd.Timestamp(end + timedelta(days=1)).tz_localize('Asia/Kuala_Lumpur').tz_convert('UTC'))


def filter_period(frame, start, end):
    lower, upper = utc_bounds(start, end)
    if frame.empty or 'ordered_at' not in frame:
        return frame.iloc[0:0].copy()
    timestamps = pd.to_datetime(frame['ordered_at'], errors='coerce', utc=True, format='mixed')
    return frame.loc[timestamps.ge(lower) & timestamps.lt(upper)].copy()


def new_state(today):
    return dict(shortcut='Today', mode='Day', start=today, end=today, day=today, week=today,
                month=today.replace(day=1), custom=(today, today), draft=(today, today),
                view=today.replace(day=1))


def switch_mode(state, mode):
    state['shortcut'] = 'Custom'
    state['mode'] = mode
    if mode == 'Custom':
        state['start'], state['end'] = state['custom']
        state['draft'] = state['custom']
        state['view'] = state['start'].replace(day=1)
    else:
        selected = state[mode.lower()]
        state['start'], state['end'] = period_bounds(mode, selected)
        state['view'] = selected.replace(day=1)


def choose_date(state, selected):
    state['shortcut'] = 'Custom'
    mode = state['mode']
    if mode == 'Custom':
        start, end = state['draft']
        # A completed range starts a new selection; an earlier click resets the start.
        state['draft'] = (selected, None) if end is not None or selected < start else (start, selected)
    else:
        state[mode.lower()] = selected
        state['start'], state['end'] = period_bounds(mode, selected)


def shift_view(state, amount, *, years=False):
    current = state['view']
    index = (current.year - 1) * 12 + current.month - 1 + amount * (12 if years else 1)
    index = max(0, min(9998 * 12 - 1, index))
    state['view'] = date(index // 12 + 1, index % 12 + 1, 1)


def apply_custom(state):
    start, end = state['draft']
    if end is None or end < start:
        return False
    state.update(start=start, end=end, custom=(start, end))
    return True


def cancel_custom(state):
    state['draft'] = state['custom']
    state['view'] = state['custom'][0].replace(day=1)


def _calendar(state, key):
    mode, view = state['mode'], state['view']
    with st.container(key='bizmar_period_calendar'):
        with st.container(key='bizmar_period_navigation'):
            previous, title, following = st.columns([1, 4, 1], vertical_alignment='center')
            previous.button(tr('‹'), key=f'{key}_previous', help='Previous year' if mode == 'Month' else 'Previous month',
                            on_click=shift_view, args=(state, -1), kwargs={'years': mode == 'Month'}, width='stretch',
                            disabled=view.year == 1 and (mode == 'Month' or view.month == 1))
            title.markdown(tr(f'**{view.year if mode == "Month" else view.strftime("%B %Y")}**'))
            following.button(tr('›'), key=f'{key}_next', help='Next year' if mode == 'Month' else 'Next month',
                             on_click=shift_view, args=(state, 1), kwargs={'years': mode == 'Month'}, width='stretch',
                             disabled=view.year == 9998 and (mode == 'Month' or view.month == 12))
        if mode == 'Month':
            with st.container(key='bizmar_period_month_grid'):
                for row in range(4):
                    for column, month in zip(st.columns(3), range(row * 3 + 1, row * 3 + 4)):
                        selected = state['month']
                        column.button(tr(calendar.month_abbr[month]), key=f'{key}_month_{month}',
                                      type='primary' if (selected.year, selected.month) == (view.year, month) else 'secondary',
                                      width='stretch', on_click=choose_date, args=(state, date(view.year, month, 1)))
        else:
            start, end = state['draft'] if mode == 'Custom' else (state['start'], state['end'])
            with st.container(key='bizmar_period_day_grid'):
                for column, label in zip(st.columns(7), ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')):
                    column.markdown(tr(f'<span class="bizmar-period-weekday">{label}</span>'), unsafe_allow_html=True)
                for week in calendar.Calendar(firstweekday=0).monthdatescalendar(view.year, view.month):
                    for column, selected in zip(st.columns(7), week):
                        with column:
                            highlighted = start <= selected <= (end or start)
                            st.button(tr(str(selected.day)), key=f'{key}_date_{selected.isoformat()}', help=selected.strftime('%A, %d %B %Y'),
                                      type='primary' if highlighted else 'secondary', width='stretch',
                                      on_click=choose_date, args=(state, selected))
            if mode == 'Week':
                st.caption(tr('Click any date to select its Monday–Sunday week.'))
            else:
                st.caption(tr(f'Start: {start:%d %b %Y} · End: {end.strftime("%d %b %Y") if end else "Select an end date"}'))
                apply, cancel = st.columns(2)
                apply.button(tr('Apply'), key=f'{key}_apply', type='primary', disabled=end is None,
                             on_click=apply_custom, args=(state,), width='stretch')
                cancel.button(tr('Cancel'), key=f'{key}_cancel', on_click=cancel_custom, args=(state,), width='stretch')


@overload
def sales_date_filter(frame: pd.DataFrame, key: str, *, return_period: Literal[True]) -> tuple[pd.DataFrame, str, date, date]: ...

@overload
def sales_date_filter(frame: pd.DataFrame, key: str, *, return_period: Literal[False] = False) -> tuple[pd.DataFrame, str]: ...

@overload
def sales_date_filter(frame: pd.DataFrame, key: str, *, return_period: bool) -> tuple[pd.DataFrame, str, date, date] | tuple[pd.DataFrame, str]: ...

def sales_date_filter(frame, key, *, return_period=False):
    today = datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).date()
    if STATE_KEY not in st.session_state:
        st.session_state[STATE_KEY] = new_state(today)
    state = st.session_state[STATE_KEY]
    st.markdown(tr('<style>' + (Path(__file__).parent / 'styles/period_filter.css').read_text(encoding='utf-8-sig') + '</style>'), unsafe_allow_html=True)
    today_col, yesterday_col, week_col, custom_col = st.columns([1, 1.25, .8, 1.35])
    shortcut = state.get('shortcut', 'Custom')
    for column, label, suffix in ((today_col, 'Today', 'today'),
                                  (yesterday_col, 'Yesterday', 'yesterday'),
                                  (week_col, '7D', '7d')):
        column.button(tr(label), key=f'{key}_{suffix}', type='primary' if shortcut == label else 'secondary',
                      on_click=_shortcut, args=(state, label, today), width='stretch')
    with custom_col:
        with st.popover(tr('Custom'), key=f'{key}_custom', type='primary' if shortcut == 'Custom' else 'secondary', width='stretch'):
            with st.container(key='bizmar_period_picker'):
                with st.container(key='bizmar_period_modes'):
                    for column, mode in zip(st.columns(4), MODES):
                        column.button(tr(mode), key=f'{key}_mode_{mode.lower()}', type='primary' if state['mode'] == mode else 'secondary',
                                      on_click=switch_mode, args=(state, mode), width='stretch')
                if state['mode'] == 'Day':
                    with st.container(key='bizmar_period_calendar'):
                        st.date_input(tr('Select day'), value=state['day'], min_value=date(1, 1, 1), max_value=date(9998, 12, 31),
                                      key=f'{key}_day_{state["day"].isoformat()}',
                                      on_change=_day_changed, args=(state, f'{key}_day_{state["day"].isoformat()}'))
                else:
                    _calendar(state, key)
    # Callbacks execute before rendering, so every consumer sees the same applied bounds.
    start, end = state['start'], state['end']
    active_mode = state['mode'] if shortcut == 'Custom' else shortcut
    st.caption(tr(f'{active_mode}: {start:%d %b %Y} – {end:%d %b %Y} (Asia/Kuala_Lumpur)'))
    filtered = filter_period(frame, start, end)
    result = (filtered, active_mode, start, end)
    return result if return_period else result[:2]


def _day_changed(state, widget_key):
    choose_date(state, st.session_state[widget_key])


def _shortcut(state, label, today):
    state['shortcut'] = label
    state['start'], state['end'] = ((today - timedelta(days=6), today) if label == '7D'
                                  else (today - timedelta(days=1),) * 2 if label == 'Yesterday'
                                  else (today, today))
