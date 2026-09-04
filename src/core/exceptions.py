class EventNotFoundError(Exception):
    """Событие не найдено."""


class EventNotPublishedError(Exception):
    """Событие не опубликовано."""


class RegistrationDeadlineError(Exception):
    """Дедлайн регистрации истёк."""


class SeatNotAvailableError(Exception):
    """Место недоступно."""


class TicketNotFoundError(Exception):
    """Билет не найден."""


class InvalidEmailError(Exception):
    """Некорректный email."""
