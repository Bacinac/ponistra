# First start

On a new installation, before it has any user, the first administrator opens their account with the code the installation command printed.

## How to use it

1. Open the installation's address in a browser; {t:setup.title} is shown.
2. Enter the {t:setup.code} that the `ponistra install` command printed.
3. Enter the {t:users.firstName}, {t:users.lastName}, {t:auth.email} and {t:auth.password}.
4. Press {t:setup.submit}.

## How it works

This page is shown instead of the sign-in only while the installation has no user. The code is compared without regard to upper and lower case, and everything but letters and digits is ignored. The account opened here is an administrator, and you are signed in to it at once.

If two people open the first account at the same time, only the first is opened; for the second the page turns to the sign-in.

Setting up the installation and the first sign-in are written to the [journal](help:admin/journal).

## Limits

- The first and last names are optional; the email address and password are not.
- An installation without a first start code refuses this form; the first account is then opened with the `manage.py createsuperuser` command on the server.

## Related

- [Users](help:admin/users)
