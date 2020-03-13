# -*- coding: utf-8 -*-
# Copyright 2014 Sébastien Alix
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)
"""Provide the :class:`Model` class which allow to access dynamically to all
methods proposed by a data model.
"""

__all__ = ['Model']

import sys

from odoorpc import error

# Python 2
if sys.version_info[0] < 3:
    # noqa: F821
    NORMALIZED_TYPES = (int, long, str, unicode)  # noqa: F821
# Python >= 3
else:
    NORMALIZED_TYPES = (int, str, bytes)


FIELDS_RESERVED = ['id', 'ids', '__odoo__', '__osv__', '__data__', 'env']


def _normalize_ids(ids):
    """Normalizes the ids argument for ``browse``."""
    if not ids:
        return []
    if ids.__class__ in NORMALIZED_TYPES:
        return [ids]
    return list(ids)


class IncrementalRecords(object):
    """A helper class used internally by __iadd__ and __isub__ methods.
    Afterwards, field descriptors can adapt their behaviour when an instance of
    this class is set.
    """

    def __init__(self, tuples):
        self.tuples = tuples


class MetaModel(type):
    """Define class methods for the :class:`Model` class."""

    _env = None

    def __getattr__(cls, method):
        """Provide a dynamic access to a RPC method."""
        if method.startswith('_'):
            return super(MetaModel, cls).__getattr__(method)

        def rpc_method(*args, **kwargs):
            """Return the result of the RPC request."""
            if cls._odoo.config['auto_context'] and 'context' not in kwargs:
                kwargs['context'] = cls.env.context
            result = cls._odoo.execute_kw(cls._name, method, args, kwargs)
            return result

        return rpc_method

    def __repr__(cls):
        return "Model(%r)" % (cls._name)

    @property
    def env(cls):
        """The environment used for this model/recordset."""
        return cls._env


# An intermediate class used to associate the 'MetaModel' metaclass to the
# 'Model' one with a Python 2 and Python 3 compatibility
BaseModel = MetaModel('BaseModel', (), {})


class Model(BaseModel):
    """Base class for all data model proxies.

    .. note::
        All model proxies (based on this class) are generated by an
        :class:`environment <odoorpc.env.Environment>`
        (see the :attr:`odoorpc.ODOO.env` property).

    .. doctest::
        :options: +SKIP

        >>> import odoorpc
        >>> odoo = odoorpc.ODOO('localhost', port=8069)
        >>> odoo.login('db_name', 'admin', 'password')
        >>> User = odoo.env['res.users']
        >>> User
        Model('res.users')

    .. doctest::
        :hide:

        >>> import odoorpc
        >>> odoo = odoorpc.ODOO(HOST, protocol=PROTOCOL, port=PORT)
        >>> odoo.login(DB, USER, PWD)
        >>> User = odoo.env['res.users']
        >>> User
        Model('res.users')

    Use this data model proxy to call any method:

    .. doctest::
        :options: +SKIP

        >>> User.name_get([2])  # Use any methods from the model class
        [[1, 'Mitchell Admin']]

    .. doctest::
        :hide:

        >>> from odoorpc.tools import v
        >>> uid = 1
        >>> if v(VERSION) >= v('12.0'):
        ...     uid = 2
        >>> data = User.name_get([uid])
        >>> 'Admin' in data[0][1]
        True

    Get a recordset:

    .. doctest::
        :options: +SKIP

        >>> user = User.browse(2)
        >>> user.name
        'Mitchell Admin'

    .. doctest::
        :hide:

        >>> from odoorpc.tools import v
        >>> uid = 1
        >>> if v(VERSION) >= v('12.0'):
        ...     uid = 2
        >>> user = User.browse(uid)
        >>> 'Admin' in user.name
        True

    And call any method from it, it will be automatically applied on the
    current record:

    .. doctest::
        :options: +SKIP

        >>> user.name_get()     # No IDs in parameter, the method is applied on the current recordset
        [[1, 'Mitchell Admin']]


    .. doctest::
        :hide:

        >>> data = user.name_get()
        >>> 'Admin' in data[0][1]
        True

    .. warning::

        Excepted the :func:`browse <odoorpc.models.Model.browse>` method,
        method calls are purely dynamic. As long as you know the signature of
        the model method targeted, you will be able to use it
        (see the :ref:`tutorial <tuto-execute-queries>`).

    """

    __metaclass__ = MetaModel
    _odoo = None
    _name = None
    _columns = {}  # {field: field object}

    def __init__(self):
        super(Model, self).__init__()
        self._env_local = None
        self._from_record = None
        self._ids = []
        self._values = {}  # {field: {ID: value}}
        self._values_to_write = {}  # {field: {ID: value}}
        for field in self._columns:
            self._values[field] = {}
            self._values_to_write[field] = {}
        self.with_context = self._with_context
        self.with_env = self._with_env

    @property
    def env(self):
        """The environment used for this model/recordset."""
        if self._env_local:
            return self._env_local
        return self.__class__._env

    @property
    def id(self):
        """ID of the record (or the first ID of a recordset)."""
        return self._ids[0] if self._ids else None

    @property
    def ids(self):
        """IDs of the recorset."""
        return self._ids

    @classmethod
    def _browse(cls, env, ids, from_record=None, iterated=None):
        """Create an instance (a recordset) corresponding to `ids` and
        attached to `env`.

        `from_record` parameter is used when the recordset is related to a
        parent record, and as such can take the value of a tuple
        (record, field). This is useful to update the parent record when the
        current recordset is modified.

        `iterated` can take the value of an iterated recordset, and no extra
        RPC queries are made to generate the resulting record (recordset and
        its record share the same values).
        """
        records = cls()
        records._env_local = env
        records._ids = _normalize_ids(ids)
        if iterated:
            records._values = iterated._values
            records._values_to_write = iterated._values_to_write
        else:
            records._from_record = from_record
            records._values = {}
            records._values_to_write = {}
            for field in cls._columns:
                records._values[field] = {}
                records._values_to_write[field] = {}
            records._init_values()
        return records

    @classmethod
    def browse(cls, ids):
        """Browse one or several records (if `ids` is a list of IDs).

        .. doctest::

            >>> odoo.env['res.partner'].browse(1)
            Recordset('res.partner', [1])

        .. doctest::
            :options: +SKIP

            >>> [partner.name for partner in odoo.env['res.partner'].browse([1, 3])]
            ['YourCompany', 'Mitchell Admin']

        .. doctest::
            :hide:

            >>> names = [partner.name for partner in odoo.env['res.partner'].browse([1, 3])]
            >>> 'YourCompany' in names[0]
            True
            >>> 'Admin' in names[1]
            True

        A list of data types returned by such record fields are
        available :ref:`here <fields>`.

        :return: a :class:`Model <odoorpc.models.Model>`
            instance (recordset)
        :raise: :class:`odoorpc.error.RPCError`
        """
        return cls._browse(cls.env, ids)

    @classmethod
    def with_context(cls, *args, **kwargs):
        """Return a model (or recordset) equivalent to the current model
        (or recordset) attached to an environment with another context.
        The context is taken from the current environment or from the
        positional arguments `args` if given, and modified by `kwargs`.

        Thus, the following two examples are equivalent:

        .. doctest::

            >>> Product = odoo.env['product.product']
            >>> Product.with_context(lang='fr_FR')
            Model('product.product')

        .. doctest::

            >>> context = Product.env.context
            >>> Product.with_context(context, lang='fr_FR')
            Model('product.product')

        This method is very convenient for example to search records
        whatever their active status are (active/inactive):

        .. doctest::

            >>> all_product_ids = Product.with_context(active_test=False).search([])

        Or to update translations of a recordset:

        .. doctest::

            >>> product_en = Product.browse(1)
            >>> product_en.env.lang
            'en_US'
            >>> product_en.name = "My product"  # Update the english translation
            >>> product_fr = product_en.with_context(lang='fr_FR')
            >>> product_fr.env.lang
            'fr_FR'
            >>> product_fr.name = "Mon produit" # Update the french translation
        """
        context = dict(args[0] if args else cls.env.context, **kwargs)
        return cls.with_env(cls.env(context=context))

    def _with_context(self, *args, **kwargs):
        """As the `with_context` class method but for recordset."""
        context = dict(args[0] if args else self.env.context, **kwargs)
        return self.with_env(self.env(context=context))

    @classmethod
    def with_env(cls, env):
        """Return a model (or recordset) equivalent to the current model
        (or recordset) attached to `env`.
        """
        new_cls = type(cls.__name__, cls.__bases__, dict(cls.__dict__))
        new_cls._env = env
        return new_cls

    def _with_env(self, env):
        """As the `with_env` class method but for recordset."""
        res = self._browse(env, self._ids)
        return res

    def _init_values(self, context=None):
        """Retrieve field values from the server.
        May be used to restore the original values in the purpose to cancel
        all changes made.
        """
        if context is None:
            context = self.env.context
        # Get basic fields (no relational ones)
        basic_fields = []
        for field_name in self._columns:
            field = self._columns[field_name]
            if not getattr(field, 'relation', False):
                basic_fields.append(field_name)
        # Fetch values from the server
        if self.ids:
            rows = self.__class__.read(
                self.ids, basic_fields, context=context, load='_classic_write'
            )
            ids_fetched = set()
            for row in rows:
                ids_fetched.add(row['id'])
                for field_name in row:
                    if field_name == 'id':
                        continue
                    self._values[field_name][row['id']] = row[field_name]
            ids_in_error = set(self.ids) - ids_fetched
            if ids_in_error:
                raise ValueError(
                    "There is no '{model}' record with IDs {ids}.".format(
                        model=self._name, ids=list(ids_in_error)
                    )
                )
        # No ID: fields filled with default values
        else:
            default_get = self.__class__.default_get(
                list(self._columns), context=context
            )
            for field_name in self._columns:
                self._values[field_name][None] = default_get.get(
                    field_name, False
                )

    def __getattr__(self, method):
        """Provide a dynamic access to a RPC *instance* method (which applies
        on the current recordset).

        .. doctest::

            >>> Partner = odoo.env['res.partner']
            >>> Partner.write([1], {'name': 'YourCompany'}) # Class method
            True
            >>> partner = Partner.browse(1)
            >>> partner.write({'name': 'YourCompany'})      # Instance method
            True

        """
        if method.startswith('_'):
            return super(Model, self).__getattr__(method)

        def rpc_method(*args, **kwargs):
            """Return the result of the RPC request."""
            args = tuple([self.ids]) + args
            if self._odoo.config['auto_context'] and 'context' not in kwargs:
                kwargs['context'] = self.env.context
            result = self._odoo.execute_kw(self._name, method, args, kwargs)
            return result

        return rpc_method

    def __getitem__(self, key):
        """If `key` is an integer or a slice, return the corresponding record
        selection as a recordset.
        """
        if isinstance(key, int) or isinstance(key, slice):
            return self._browse(self.env, self._ids[key], iterated=self)
        else:
            return getattr(self, key)

    def __int__(self):
        return self.id

    def __eq__(self, other):
        return other.__class__ == self.__class__ and self.id == other.id

    # Need to explicitly declare '__hash__' in Python 3
    # (because '__eq__' is defined)
    __hash__ = BaseModel.__hash__

    def __ne__(self, other):
        return other.__class__ != self.__class__ or self.id != other.id

    def __repr__(self):
        return "Recordset({!r}, {})".format(self._name, self.ids)

    def __iter__(self):
        """Return an iterator over `self`."""
        for id_ in self._ids:
            yield self._browse(self.env, id_, iterated=self)

    def __nonzero__(self):
        return bool(getattr(self, '_ids', True))

    def __len__(self):
        return len(self.ids)

    def __iadd__(self, records):
        if not self._from_record:
            raise error.InternalError("No parent record to update")
        try:
            list(records)
        except TypeError:
            records = [records]
        parent = self._from_record[0]
        field = self._from_record[1]
        updated_values = parent._values_to_write[field.name]
        values = []
        if updated_values.get(parent.id):
            values = updated_values[parent.id][:]  # Copy
        from odoorpc import fields

        for id_ in fields.records2ids(records):
            if (3, id_) in values:
                values.remove((3, id_))
            if (4, id_) not in values:
                values.append((4, id_))
        return IncrementalRecords(values)

    def __isub__(self, records):
        if not self._from_record:
            raise error.InternalError("No parent record to update")
        try:
            list(records)
        except TypeError:
            records = [records]
        parent = self._from_record[0]
        field = self._from_record[1]
        updated_values = parent._values_to_write[field.name]
        values = []
        if updated_values.get(parent.id):
            values = updated_values[parent.id][:]  # Copy
        from odoorpc import fields

        for id_ in fields.records2ids(records):
            if (4, id_) in values:
                values.remove((4, id_))
            if (3, id_) not in values:
                values.append((3, id_))
        return values
