"""Authenticated Streamlit controls for dry-run and Google Sheets polling."""
from display_preferences import tr
import pandas as pd
import streamlit as st

import google_sheets_connection
import google_sheets_sync
import orders_store


_PREVIEW_KEY = 'google_sheets_sync_preview'
_PENDING_KEY = 'google_sheets_pending_review'


def _show_preview(prepared, *, acknowledge=False, key_prefix='google_sheets'):
    preview = prepared.preview
    for error in preview.errors[:20]:
        st.error(tr(error))
    if len(preview.errors) > 20:
        st.caption(tr(f'{len(preview.errors) - 20} additional validation issues.'))
    for warning in preview.ambiguous_rows[:20]:
        st.warning(tr(warning))
    if preview.product_mappings:
        st.dataframe(
            pd.DataFrame(
                preview.product_mappings,
                columns=['Google Forms quantity column', 'Catalogue product'],
            ),
            hide_index=True,
            width='stretch',
        )
    if preview.records:
        summary = [
            {
                'Row': record['source_row'],
                'Customer': record['customer']['name'],
                'Fulfilment': record['fulfilment_method'],
                'Products': ', '.join(
                    f"{line['quantity']} x {prepared.product_names.get(int(line['product_id']), f'Product #{line['product_id']}')}"
                    for line in record['lines']
                ),
                'Product subtotal (RM)': f"{record['subtotal']:.2f}",
                'Action':f'Link {record["existing_order_reference"]} without changes' if record.get('existing_order_id') else 'Create new order',
            }
            for record in preview.records
        ]
        st.dataframe(pd.DataFrame(summary), hide_index=True, width='stretch')
        new=[r for r in preview.records if not r.get('existing_order_id')]
        st.info(
            tr(f"{len(new)} new order(s) · {len(preview.records)-len(new)} existing-order association(s) · "
            f"RM {sum(record['subtotal'] for record in new):,.2f} new product subtotal. "
            'New orders will be Pending and Unpaid; submitted payment amounts are not verified payments.')
        )
        linked=[r for r in preview.records if r.get('existing_order_id')]
        if linked:
            with st.expander(tr('Review existing-order associations')):
                for record in linked:
                    existing=orders_store.details(record['existing_order_id'])
                    if existing:
                        st.write(f"Response row {record['source_row']} → {existing['order']['order_code']}")
                        st.caption(tr('Existing order will be preserved, including manual edits and recorded payments.'))
                        st.write(tr('Form customer:'),record['customer']['name'])
                        st.write(tr('Existing customer:'),existing['order']['customer_name'])
                        st.write(tr('Existing products:'),', '.join(f"{line['quantity']} × {line['product_name']}" for line in existing['items']))
    if preview.already_imported:
        st.caption(tr(f'{len(preview.already_imported)} previously synchronized response(s) will be skipped.'))
    return bool(preview.records) and not preview.errors and (
        not preview.ambiguous_rows or acknowledge
    )


def _commit_confirmed(config, prepared, *, acknowledge_ambiguous=False):
    fresh=google_sheets_sync.verify_preview(config,prepared)
    if fresh.preview.errors or fresh.preview.ambiguous_rows and not acknowledge_ambiguous:
        raise google_sheets_sync.SyncReviewRequired('Review the preview before enabling live synchronization.',fresh)
    return orders_store.activate_google_sheets_preview(config.spreadsheet_id,fresh.sheet_id,fresh.preview.records,
        allow_identical_rows=acknowledge_ambiguous)


def _run_poll(config, *, force=False):
    try:
        result = google_sheets_sync.synchronize(config,force=force)
        review_preview=result.pop('review_preview',None)
        if force and not result.get('waiting') and not result.get('syncing'):
            st.session_state['google_sheets_manual_result']=result
        if not result.get('waiting') and not result.get('syncing'):
            st.session_state['google_sheets_connected'] = True
            if review_preview is not None:
                st.session_state[_PENDING_KEY]=review_preview
            else:
                st.session_state.pop(_PENDING_KEY, None)
            st.session_state.pop('google_sheets_sync_error',None)
        revision=orders_store.order_data_revision()
        previous=st.session_state.get('google_sheets_data_revision')
        st.session_state['google_sheets_data_revision']=revision
        if result.get('imported', 0) or previous is not None and previous!=revision:
            st.cache_data.clear()
            st.rerun()
        return result
    except google_sheets_sync.SyncReviewRequired as error:
        st.session_state['google_sheets_connected'] = True
        st.session_state[_PENDING_KEY] = error.preview
        st.session_state['google_sheets_sync_error'] = google_sheets_sync.safe_sync_error(error)
    except google_sheets_connection.GoogleSheetsConnectionError as error:
        st.session_state['google_sheets_connected'] = False
        st.session_state['google_sheets_sync_error'] = google_sheets_sync.safe_sync_error(error)
    except Exception as error:
        st.session_state['google_sheets_sync_error'] = google_sheets_sync.safe_sync_error(error)
    return None


@st.fragment(run_every='30s')
def render_sync_background(page,navigate_to):
    """Keep the existing owner-session timer active without a global monitor panel."""
    import os
    if os.environ.get('BIZMAR_PREVIEW_ONLY')=='1':
        return
    try:
        orders_store.current_owner()
    except PermissionError:
        return
    try:
        config=google_sheets_connection.load_config(st.secrets)
        state=orders_store.google_sheets_sync_state(config.spreadsheet_id)
        # The monitor's own fragment performs this tick when that page is open.
        if page!='Data Import' and state and state.get('confirmed_at'):
            _run_poll(config)
    except google_sheets_connection.GoogleSheetsConnectionError:
        if page=='Overview':
            st.warning(tr('Google Sheets connection is unavailable. Review Data Import → Google Sheets Sync.'))


@st.fragment(run_every='30s')
def render_google_sheets_sync():
    try:
        orders_store.current_owner()
    except PermissionError:
        return
    with st.expander(tr('Google Sheets Sync'),expanded=True):
        st.markdown(tr('#### Google Sheets Sync Monitor'))
        try:
            config = google_sheets_connection.load_config(st.secrets)
            state = orders_store.google_sheets_sync_state(config.spreadsheet_id)
        except google_sheets_connection.GoogleSheetsConnectionError as error:
            st.warning(tr(f'Google Sheets is not configured: {error}'))
            return
        except Exception as error:
            st.error(tr('Sync status is unavailable. Review the configuration or sign in again.'))
            return

        identity=(config.spreadsheet_id,config.worksheet_name)
        import os
        if os.environ.get('BIZMAR_PREVIEW_ONLY') == '1':
            st.info(tr('Preview only: live sync is OFF. Orders and notifications are read-only.'))
            if st.button(tr('Preview Google Sheet'), key='google_sheets_readonly_preview'):
                try:
                    snapshot = google_sheets_connection.read_snapshot(config)
                    st.session_state[_PREVIEW_KEY] = google_sheets_sync.prepare_preview(snapshot, config.spreadsheet_id)
                except Exception as error:
                    st.error(tr(google_sheets_sync.safe_sync_error(error)))
            if st.session_state.get(_PREVIEW_KEY):
                _show_preview(st.session_state[_PREVIEW_KEY], key_prefix='google_sheets_readonly')
            return
        if st.session_state.get('google_sheets_config_identity')!=identity:
            for key in (_PREVIEW_KEY,_PENDING_KEY,'google_sheets_sync_error','google_sheets_connected','google_sheets_data_revision'):
                st.session_state.pop(key,None)
            st.session_state['google_sheets_config_identity']=identity

        confirmed = bool(state and state.get('confirmed_at'))
        if confirmed:
            result = _run_poll(config)
            if result and result.get('syncing'):
                st.info(tr('Syncing in another BizMar session…'))
            elif result and result.get('imported', 0):
                st.success(tr(f"{result['imported']} new order(s) synchronized."))
                state = orders_store.google_sheets_sync_state(config.spreadsheet_id)
            elif result is not None:
                state = orders_store.google_sheets_sync_state(config.spreadsheet_id)

        from sync_monitor_ui import render_monitor_cards,render_history
        data,model=render_monitor_cards(config)
        render_history(data)
        syncing=bool(state and state.get('lease_until') and state['lease_until']>orders_store.now())
        manual_result=st.session_state.pop('google_sheets_manual_result',None)
        if manual_result:
            st.success(tr(f"Sync completed: {manual_result['imported']} imported, {manual_result.get('skipped',0)} skipped, {manual_result.get('linked',0)} associated, {manual_result.get('failed',0)} failed."))
        if state and state.get('last_error'):
            st.error(tr(f"Sync needs attention: {state['last_error']}"))
        if st.session_state.get('google_sheets_sync_error'):
            st.error(tr(f"Sync needs attention: {st.session_state['google_sheets_sync_error']}"))

        actions = st.columns(3)
        if not confirmed:
            if actions[0].button(tr('Preview Google Sheet'), key='google_sheets_preview'):
                try:
                    snapshot = google_sheets_connection.read_snapshot(config)
                    st.session_state['google_sheets_connected'] = True
                    st.session_state[_PREVIEW_KEY] = google_sheets_sync.prepare_preview(
                        snapshot, config.spreadsheet_id,
                    )
                    st.session_state.pop('google_sheets_sync_error', None)
                except Exception as error:
                    st.session_state['google_sheets_sync_error'] = google_sheets_sync.safe_sync_error(error)
        elif actions[0].button(tr('Sync Now'), key='google_sheets_sync_now',disabled=syncing):
            with st.spinner('Synchronizing Google Sheets…'):
                result = _run_poll(config,force=True)
            if not result or not result.get('syncing'):
                st.rerun()
            if result.get('syncing'):
                st.info(tr('Another owner session is synchronizing. No overlapping attempt was started.'))
            if result and result.get('imported', 0):
                st.success(tr(f"{result['imported']} new order(s) synchronized."))
                st.rerun()

        if confirmed:
            if actions[1].button(tr('Pause Sync'), key='google_sheets_pause'):
                orders_store.pause_google_sheets_sync(config.spreadsheet_id)
                st.session_state.pop(_PENDING_KEY, None)
                st.rerun()

        prepared = st.session_state.get(_PREVIEW_KEY) if not confirmed else None
        if prepared:
            st.markdown(tr('**Dry-run preview — no orders have been saved.**'))
            ambiguous_ack = False
            if prepared.preview.ambiguous_rows:
                ambiguous_ack = st.checkbox(
                    tr('I reviewed every flagged row and approve its displayed action, including existing-order associations.'),
                    key=f'google_sheets_ambiguous_{prepared.signature[:12]}',
                )
            reviewed = st.checkbox(
                tr('I reviewed the mapped columns, products, order values and delivery details.'),
                key=f'google_sheets_reviewed_{prepared.signature[:12]}',
            )
            approved=st.checkbox(tr('I approve enabling live automatic synchronization and importing the reviewed responses.'),key=f'google_sheets_live_approval_{prepared.signature[:12]}')
            can_confirm = _show_preview(
                prepared, acknowledge=ambiguous_ack, key_prefix='google_sheets_preview',
            )
            if st.button(
                tr('Confirm Import and Enable Auto Sync'),
                type='primary',
                disabled=not ((can_confirm or bool(prepared.preview.already_imported) and not prepared.preview.errors and not prepared.preview.ambiguous_rows) and reviewed and approved),
                key='google_sheets_confirm_import',
            ):
                try:
                    result = _commit_confirmed(
                        config, prepared, acknowledge_ambiguous=ambiguous_ack,
                    )
                    st.session_state.pop(_PREVIEW_KEY, None)
                    st.session_state.pop(_PENDING_KEY, None)
                    st.session_state.pop('google_sheets_sync_error', None)
                    st.cache_data.clear()
                    st.success(tr(f"{result['imported']} new order(s) imported; {result.get('linked',0)} existing response(s) linked without changes. Automatic sync is enabled."))
                    st.rerun()
                except Exception as error:
                    st.session_state['google_sheets_sync_error'] = google_sheets_sync.safe_sync_error(error)
                    st.error(tr(google_sheets_sync.safe_sync_error(error)))

        pending = st.session_state.get(_PENDING_KEY) if confirmed else None
        if pending:
            st.markdown(tr('**Rows require review — no automatic import was performed.**'))
            ack = False
            if pending.preview.ambiguous_rows:
                ack = st.checkbox(
                    tr('I reviewed every flagged row and approve its displayed action, including existing-order associations.'),
                    key=f'google_sheets_pending_ambiguous_{pending.signature[:12]}',
                )
            _show_preview(pending, acknowledge=ack, key_prefix='google_sheets_pending')
            if st.button(
                tr('Import Reviewed Rows'),
                disabled=bool(pending.preview.errors) or (
                    bool(pending.preview.ambiguous_rows) and not ack
                ),
                key='google_sheets_import_reviewed',
            ):
                lease = orders_store.acquire_google_sheets_lease(
                    config.spreadsheet_id, pending.sheet_id,trigger='Manual',
                )
                if lease:
                    try:
                        pending=google_sheets_sync.verify_preview(config,pending)
                        result = google_sheets_sync.commit_preview(
                            config, pending, acknowledge_ambiguous=ack,lease_token=lease,
                        )
                        orders_store.finish_google_sheets_sync(
                            config.spreadsheet_id, lease, new_orders=result['imported'],associated=result.get('linked',0),skipped=len(pending.preview.already_imported),
                        )
                        st.session_state.pop(_PENDING_KEY, None)
                        st.cache_data.clear()
                        st.success(tr(f"{result['imported']} reviewed order(s) imported."))
                        st.rerun()
                    except Exception as error:
                        orders_store.finish_google_sheets_sync(
                            config.spreadsheet_id, lease, error=google_sheets_sync.safe_sync_error(error),
                        )
                        st.error(tr(google_sheets_sync.safe_sync_error(error)))
                else:
                    st.info(tr('Another session is synchronizing this sheet. Try again shortly.'))
