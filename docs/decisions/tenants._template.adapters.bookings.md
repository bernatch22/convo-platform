# `tenants._template.adapters.bookings`

The reasoning that used to live in the docstrings of `tenants/_template/adapters/bookings.py`; the code keeps one line per symbol.

## module

It stands where your real back office will stand and answers the same shape: a
capability name, a dict of arguments, a plain result. Reading is `find_booking`;
writing is `cancel_booking` and its inverse `restore_booking`, which the saga
runs when the cancellation could not be confirmed to the customer.

TODO(copy): replace each method with an HTTP call to your own API and keep
`capabilities()` and the result shapes. Every layer above — tool, guard, saga,
executor, prompt — then works unchanged. An argument the system cannot read
raises `ValueError`, which the executor turns into a sentence the caller hears;
never a stack trace, and never a silent success.
