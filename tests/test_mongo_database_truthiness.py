from app.database import job_io, mongo


class _Collection:
    def create_index(self, *_args, **_kwargs):
        return None

    def find(self, *_args, **_kwargs):
        return []


class _Database:
    def __getattr__(self, _name):
        return _Collection()

    def __bool__(self):
        raise NotImplementedError(
            "Database objects do not implement truth value testing"
        )


def test_ensure_indexes_accepts_database_without_truth_testing():
    mongo.ensure_indexes(_Database())


def test_load_stocks_accepts_database_without_truth_testing():
    assert job_io.load_stocks(_Database()) == []
