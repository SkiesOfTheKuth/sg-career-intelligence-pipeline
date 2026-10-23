"""Presence semantics for retained MyCareersFuture source fields."""

def source_field_supplied(raw, field):
    """Use original API key presence, not the normalizer's empty defaults.

    Explicit null/empty values mean the source currently supplies no value;
    absent keys leave retained content untouched. Custom normalized records use
    their own key presence. The collector retains raw_response verbatim.
    """
    response = raw.get('raw_response')
    if not isinstance(response, dict):
        if field == 'salary':
            return any(key in raw for key in ('salary_min', 'salary_max', 'advertised_salary'))
        return field in raw
    keys = {'company': 'postedCompany', 'location': 'addresses', 'employment_type': 'employmentTypes'}
    if field in ('posted_date', 'expiry_date'):
        metadata = response.get('metadata') or {}
        return ('originalPostingDate' if field == 'posted_date' else 'expiryDate') in metadata
    return keys.get(field, field) in response
