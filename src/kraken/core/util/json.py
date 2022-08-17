import datetime

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.Z"


def dt2json(dt: datetime.datetime) -> str:
    return dt.strftime(DATETIME_FORMAT)


def json2dt(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, DATETIME_FORMAT)
