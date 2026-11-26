"""Google Forms delivery policy and shared financial projection."""
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd

AWAITING = 'Awaiting Rider Quote'


def amount(value):
    try:
        value=Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    except Exception:
        raise ValueError('Enter a valid non-negative RM amount.') from None
    if not value.is_finite() or not 0<=value<=Decimal('999999999.99'):
        raise ValueError('Enter a valid non-negative RM amount.')
    return value


def delivery_policy(subtotal, method, quote=None, rider_cost=None):
    subtotal=amount(subtotal)
    if method not in ('Pickup','Delivery'):
        raise ValueError('Choose Pickup or Delivery.')
    free=method=='Delivery' and subtotal>=100
    pending=method=='Delivery' and not free and quote is None
    fee=Decimal(0) if method=='Pickup' or free or pending else amount(quote)
    return dict(delivery_fee=float(fee),delivery_quote_status=AWAITING if pending else 'Confirmed',
        free_delivery_applied=int(free),rider_cost=float(amount(rider_cost)) if rider_cost is not None and method=='Delivery' else None,
        final_payable_amount=None if pending else float(subtotal+fee))


def quote_pending(order):
    return order.get('delivery_quote_status')==AWAITING


def apply_delivery_financials(frame, cost_column='cost'):
    """Keep order counts, but exclude unconfirmed amounts from financial sums."""
    result=frame.copy()
    pending=result.get('delivery_quote_status',pd.Series('',index=result.index)).eq(AWAITING)
    rider=pd.to_numeric(result.get('rider_cost',pd.Series(0.,index=result.index)),errors='coerce').fillna(0)
    result[cost_column]=result[cost_column]+rider
    result.loc[pending,['revenue',cost_column]]=0.
    return result
