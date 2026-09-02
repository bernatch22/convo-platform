# `tenants.tienda-sur.adapters.orderbook`

The reasoning that used to live in the docstrings of `tenants/tienda-sur/adapters/orderbook.py`; the code keeps one line per symbol.

## module

A call about an order starts from an order that exists, so the fake system has
to know a handful of customers before anyone picks up the phone. Real
e-commerce back offices look an order up by its number and confirm it with the
phone the order was placed with; so does `lookup`, and it accepts either — a
customer reading the number off an e-mail and a customer who only has their
phone both get found, which is what happens on a real line.

Never real data: the names are invented and the phone numbers are in the
Spanish 600-block reserved for fiction. A customer replaces this module with
their own order API and keeps `lookup`'s two arguments and the result shape.

## lookup

The number wins when both are given: it identifies one order, while a phone
identifies a customer who may have several — and when only a phone arrives,
the most recent order is the one they are calling about.
