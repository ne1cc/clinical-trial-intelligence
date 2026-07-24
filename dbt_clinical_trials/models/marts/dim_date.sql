-- Calendar spine covering registry history through near-term planning horizon.
select
    cast(d as date) as date_day,
    extract(year from d) as year,
    extract(month from d) as month,
    extract(quarter from d) as quarter,
    cast(date_trunc('month', d) as date) as month_start_date,
    cast(date_trunc('quarter', d) as date) as quarter_start_date,
    strftime(d, '%Y-%m') as year_month,
    dayname(cast(d as date)) as day_name,
    (extract(isodow from d) in (6, 7)) as is_weekend
from generate_series(
    date '1999-01-01',
    current_date + interval 3 year,
    interval 1 day
) as t(d)
