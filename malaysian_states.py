"""Canonical Malaysian state values and safe legacy-name normalization."""
import re

STATES = (
    'Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang',
    'Perak', 'Perlis', 'Pulau Pinang', 'Selangor', 'Terengganu', 'Sabah',
    'Sarawak', 'Wilayah Persekutuan Kuala Lumpur',
    'Wilayah Persekutuan Putrajaya', 'Wilayah Persekutuan Labuan',
)
UNSPECIFIED = 'Not Specified'
CHOICES = (UNSPECIFIED, *STATES)


def _key(value):
    text = '' if value is None else str(value)
    return re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()


_CANONICAL = {_key(state): state for state in STATES}
_ALIASES = {
    'johore': 'Johor',
    'kedah darul aman': 'Kedah',
    'kelantan darul naim': 'Kelantan',
    'malacca': 'Melaka',
    'negeri sembilan darul khusus': 'Negeri Sembilan',
    'pahang darul makmur': 'Pahang',
    'penang': 'Pulau Pinang',
    'p pinang': 'Pulau Pinang',
    'perlis indra kayangan': 'Perlis',
    'perak darul ridzuan': 'Perak',
    'sabah negeri di bawah bayu': 'Sabah',
    'sarawak bumi kenyalang': 'Sarawak',
    'selangor darul ehsan': 'Selangor',
    'terengganu darul iman': 'Terengganu',
    'kl': 'Wilayah Persekutuan Kuala Lumpur',
    'kuala lumpur': 'Wilayah Persekutuan Kuala Lumpur',
    'wp kuala lumpur': 'Wilayah Persekutuan Kuala Lumpur',
    'w p kuala lumpur': 'Wilayah Persekutuan Kuala Lumpur',
    'federal territory of kuala lumpur': 'Wilayah Persekutuan Kuala Lumpur',
    'putrajaya': 'Wilayah Persekutuan Putrajaya',
    'wp putrajaya': 'Wilayah Persekutuan Putrajaya',
    'w p putrajaya': 'Wilayah Persekutuan Putrajaya',
    'federal territory of putrajaya': 'Wilayah Persekutuan Putrajaya',
    'labuan': 'Wilayah Persekutuan Labuan',
    'wp labuan': 'Wilayah Persekutuan Labuan',
    'w p labuan': 'Wilayah Persekutuan Labuan',
    'federal territory of labuan': 'Wilayah Persekutuan Labuan',
}
_ALIASES = {_key(alias): state for alias, state in _ALIASES.items()}


def canonical(value):
    """Return a canonical state for a known value or legacy alias, else ``None``."""
    key = _key(value)
    if not key or key == _key(UNSPECIFIED):
        return None
    return _CANONICAL.get(key, _ALIASES.get(key))


def normalize(value):
    """Normalize a recognized value; preserve blanks and reject unknown states."""
    if value is None or not str(value).strip():
        return ''
    if _key(value) == _key(UNSPECIFIED):
        return ''
    state = canonical(value)
    if state is None:
        raise ValueError('Select a Malaysian state or Not Specified.')
    return state


def display(value):
    """Format saved values without hiding unknown or missing data as a real state."""
    return canonical(value) or UNSPECIFIED


def destination(order):
    # Delivery snapshots never fall back to residence. Legacy orders stay unknown.
    field = 'delivery_state' if order.get('fulfilment_method') == 'Delivery' else 'customer_state_snapshot'
    return display(order.get(field))
