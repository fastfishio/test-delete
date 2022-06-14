from jsql import sql
from noonutil.v1.sqlutil import assert_scalar

from liborder import ctx


# todo: this has been copied from mp-food-api repo
#  where they use id_status, and we use status_code, so some changes may be needed..
class Status(object):
    TABLE = None
    PK = None
    KEY = 'code'

    def __init__(self, id, ctx={}):
        self.id = id
        self.ctx = ctx

    def get_state(self, lock=False):
        lock = False
        code = sql(ctx.conn, '''
            SELECT {{key}} FROM {{table}} WHERE {{pk}}=:id {% if lock %}FOR UPDATE{% endif %}
        ''', lock=lock, id=self.id, table=self.TABLE, pk=self.PK, key=self.KEY).scalar()
        assert code, f"unknown code: {code}"
        return code
        # return get_code_by_id('status', code)

    def update_state(self, from_state, to_state):
        # id_state = get_id_by_code('status', to_state)
        sql(ctx.conn, '''
            UPDATE {{table}} t
            SET {{key}}=:id_state
            WHERE {{pk}}=:id
        ''', id=self.id, id_state=to_state, table=self.TABLE, pk=self.PK, key=self.KEY)
        # sqlutil.insert_one(ctx.conn, models.tables.StatusHistory, {'table_name': self.TABLE,
        #                                                            'pk_column': self.id,
        #                                                            'id_status': id_state,
        #                                                            'ctx': json.dumps(self.ctx)})

    def assert_state(self, states):
        assert_scalar(states, 'invalid state {} {} {}'.format(self.TABLE, self.id, states), ctx.conn, '''
            SELECT s.code FROM {{table}} t LEFT JOIN status s ON s.code = t.{{key}} WHERE {{pk}}=:id
        ''', id=self.id, table=self.TABLE, pk=self.PK, key=self.KEY)

    @classmethod
    def get_transitions(cls, from_state):
        def helper():
            prefix = f'{from_state}_to_'
            for k in dir(cls):
                if k.startswith(f'{from_state}_to_'):
                    yield k.replace(prefix, '')

        return list(helper())

    def is_allowed(self, to_state):
        from_state = self.get_state(lock=True)
        tx = '{}_to_{}'.format(from_state, to_state)
        fn = getattr(self, tx, None)
        if fn:
            return True
        return False

    def transition(self, to_state, *, ignore_error=False, allow_noop=False, ignore_not_allowed=False):
        from_state = self.get_state(lock=True)
        if allow_noop and (to_state == from_state): return
        tx = '{}_to_{}'.format(from_state, to_state)
        fn = getattr(self, tx, None)
        if not fn and ignore_not_allowed: return
        if not fn and not self.status_check_enabled(): return
        assert fn, f'not allowed transition {tx}'
        self.assert_state(from_state)
        try:
            fn()  # pylint: disable=not-callable
        except AssertionError:
            if ignore_error: return False
            raise
        self.update_state(from_state, to_state)
        tx = 'after_{}'.format(to_state)
        fn = getattr(self, tx, None)
        if fn:
            fn()
        final_fn = getattr(self, 'called_after_status_change', None)
        if final_fn:
            final_fn(to_state)
        return True

    def new_to_new(self):
        # allow this transition to log transition when object is created
        pass

    def status_check_enabled(self):
        return True
