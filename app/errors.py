# app/errors.py 
# provide custom exceptions for the application
class AccountNotFound(Exception): pass
class InsufficientFunds(Exception): pass
class InvalidAmount(Exception): pass
class SameAccount(Exception): pass
class InvalidOwner(Exception): pass
class OwnerTaken(Exception): pass
class IdempotencyKeyReused(Exception): pass