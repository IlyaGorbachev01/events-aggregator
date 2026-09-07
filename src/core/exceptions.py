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


class ProviderUnavailableError(Exception):
    """Провайдер событий недоступен (5xx)."""


class ProviderAuthError(Exception):
    """Ошибка аутентификации с провайдером (401)."""
