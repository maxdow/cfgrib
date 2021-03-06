#
# Copyright 2017-2019 European Centre for Medium-Range Weather Forecasts (ECMWF).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Authors:
#   Alessandro Amici - B-Open - https://bopen.eu
#

from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import bytes, float, int, isinstance
from future.utils import raise_from

import functools
import logging
import pkgutil
import typing as T  # noqa

import cffi

LOG = logging.getLogger(__name__)


ffi = cffi.FFI()
ffi.cdef(
    pkgutil.get_data(__name__, 'grib_api.h').decode('utf-8') +
    pkgutil.get_data(__name__, 'eccodes.h').decode('utf-8')
)


class RaiseOnAttributeAccess(object):
    def __init__(self, exc, message):
        self.message = message
        self.exc = exc

    def __getattr__(self, attr):
        raise_from(RuntimeError(self.message), self.exc)


for libname in ['eccodes', 'libeccodes.so', 'libeccodes']:
    try:
        lib = ffi.dlopen(libname)
        LOG.info("ecCodes library found using name '%s'.", libname)
        break
    except OSError as exc:
        # lazy exception
        lib = RaiseOnAttributeAccess(exc, 'ecCodes library not found on the system.')
        LOG.info("ecCodes library not found using name '%s'.", libname)


# default encoding for ecCodes strings
ENC = 'ascii'

#
# from gribapi.py
#
CODES_PRODUCT_ANY = 0
""" Generic product kind """
CODES_PRODUCT_GRIB = 1
""" GRIB product kind """
CODES_PRODUCT_BUFR = 2
""" BUFR product kind """
CODES_PRODUCT_METAR = 3
""" METAR product kind """
CODES_PRODUCT_GTS = 4
""" GTS product kind """
CODES_PRODUCT_TAF = 5
""" TAF product kind """

# Constants for 'missing'
GRIB_MISSING_DOUBLE = -1e+100
GRIB_MISSING_LONG = 2147483647

CODES_MISSING_DOUBLE = GRIB_MISSING_DOUBLE
CODES_MISSING_LONG = GRIB_MISSING_LONG

#
# Helper values to discriminate key types
#
CODES_TYPE_UNDEFINED = lib.GRIB_TYPE_UNDEFINED
CODES_TYPE_LONG = lib.GRIB_TYPE_LONG
CODES_TYPE_DOUBLE = lib.GRIB_TYPE_DOUBLE
CODES_TYPE_STRING = lib.GRIB_TYPE_STRING
CODES_TYPE_BYTES = lib.GRIB_TYPE_BYTES
CODES_TYPE_SECTION = lib.GRIB_TYPE_SECTION
CODES_TYPE_LABEL = lib.GRIB_TYPE_LABEL
CODES_TYPE_MISSING = lib.GRIB_TYPE_MISSING

CODES_KEYS_ITERATOR_ALL_KEYS = 0
CODES_KEYS_ITERATOR_SKIP_READ_ONLY = (1 << 0)
CODES_KEYS_ITERATOR_SKIP_OPTIONAL = (1 << 1)
CODES_KEYS_ITERATOR_SKIP_EDITION_SPECIFIC = (1 << 2)
CODES_KEYS_ITERATOR_SKIP_CODED = (1 << 3)
CODES_KEYS_ITERATOR_SKIP_COMPUTED = (1 << 4)
CODES_KEYS_ITERATOR_SKIP_DUPLICATES = (1 << 5)
CODES_KEYS_ITERATOR_SKIP_FUNCTION = (1 << 6)
CODES_KEYS_ITERATOR_DUMP_ONLY = (1 << 7)


#
# Helper functions for error reporting
#
def grib_get_error_message(code):
    # type: (int) -> str
    message = lib.grib_get_error_message(code)
    return ffi.string(message).decode(ENC)


class EcCodesError(Exception):
    def __init__(self, code, message=None, *args):
        self.code = code
        self.eccode_message = grib_get_error_message(code)
        if message is None:
            message = '%s (%s).' % (self.eccode_message, code)
        super(EcCodesError, self).__init__(message, code, *args)


def check_last(func):

    @functools.wraps(func)
    def wrapper(*args):
        code = ffi.new('int *')
        args += (code,)
        retval = func(*args)
        if code[0] != lib.GRIB_SUCCESS:
            raise EcCodesError(code[0])
        return retval

    return wrapper


def check_return(func):

    @functools.wraps(func)
    def wrapper(*args):
        code = func(*args)
        if code != lib.GRIB_SUCCESS:
            raise EcCodesError(code)

    return wrapper


#
# CFFI reimplementation of gribapi.py functions with codes names
#
def codes_index_new_from_file(path, keys):
    # type: (bytes, T.Iterable[bytes]) -> cffi.FFI.CData
    keys_enc = b','.join(keys)
    return check_last(lib.codes_index_new_from_file)(ffi.NULL, path, keys_enc)


def codes_handle_new_from_file(fileobj, product_kind=CODES_PRODUCT_GRIB, context=None):
    if context is None:
        context = ffi.NULL
    try:
        retval = check_last(lib.codes_handle_new_from_file)(context, fileobj, product_kind)
        if retval == ffi.NULL:
            raise EOFError("End of file: %r" % fileobj)
        else:
            return retval
    except EcCodesError as ex:
        if ex.code == lib.GRIB_END_OF_FILE:
            raise EOFError("End of file: %r" % fileobj)
        raise


def codes_handle_clone(handle):
    # type: (cffi.FFI.CData) -> cffi.FFI.CData
    cloned_handle = lib.codes_handle_clone(handle)
    if cloned_handle is ffi.NULL:
        raise EcCodesError(lib.GRIB_NULL_POINTER)
    return cloned_handle


codes_index_delete = lib.codes_index_delete
codes_handle_delete = lib.codes_handle_delete


def codes_new_from_index(indexid):
    # type: (cffi.FFI.CData) -> cffi.FFI.CData
    return check_last(lib.codes_handle_new_from_index)(indexid)


def codes_index_get_size(indexid, key):
    # type: (cffi.FFI.CData, bytes) -> int
    """
    Get the number of coded value from a key.
    If several keys of the same name are present, the total sum is returned.

    :param bytes key: the keyword to get the size of

    :rtype: int
    """
    size = ffi.new('size_t *')
    codes_index_get_size = check_return(lib.codes_index_get_size)
    codes_index_get_size(indexid, key, size)
    return size[0]


def codes_index_get_long(indexid, key):
    # type: (cffi.FFI.CData, bytes) -> T.List[int]
    """
    Get the list of integer values associated to a key.
    The index must be created with such a key (possibly together with other
    keys).

    :param bytes key: the keyword whose list of values has to be retrieved

    :rtype: List(int)
    """
    size = codes_index_get_size(indexid, key)
    values = ffi.new('long[]', size)
    size_p = ffi.new('size_t *', size)
    check_return(lib.codes_index_get_long)(indexid, key, values, size_p)
    return list(values)


def codes_index_get_double(indexid, key):
    # type: (cffi.FFI.CData, bytes) -> T.List[float]
    """
    Get the list of double values associated to a key.
    The index must be created with such a key (possibly together with other
    keys).

    :param bytes key: the keyword whose list of values has to be retrieved

    :rtype: List(int)
    """
    size = codes_index_get_size(indexid, key)
    values = ffi.new('double[]', size)
    size_p = ffi.new('size_t *', size)
    check_return(lib.codes_index_get_double)(indexid, key, values, size_p)
    return list(values)


def codes_index_get_string(indexid, key, length=256):
    # type: (cffi.FFI.CData, bytes, int) -> T.List[bytes]
    """
    Get the list of string values associated to a key.
    The index must be created with such a key (possibly together with other
    keys).

    :param bytes key: the keyword whose list of values has to be retrieved

    :rtype: List(int)
    """
    size = codes_index_get_size(indexid, key)
    values_keepalive = [ffi.new('char[]', length) for _ in range(size)]
    values = ffi.new('const char *[]', values_keepalive)
    size_p = ffi.new('size_t *', size)
    codes_index_get_string = check_return(lib.codes_index_get_string)
    codes_index_get_string(indexid, key, values, size_p)
    return [ffi.string(values[i]) for i in range(size_p[0])]


def codes_index_get(indexid, key, ktype=bytes):
    # type: (cffi.FFI.CData, bytes, type) -> list
    if ktype is int:
        result = codes_index_get_long(indexid, key)  # type: T.List[T.Any]
    elif ktype is float:
        result = codes_index_get_double(indexid, key)
    elif ktype is bytes:
        result = codes_index_get_string(indexid, key)
    else:
        raise TypeError("ktype not supported %r" % ktype)
    return result


def codes_index_select_long(indexid, key, value):
    # type: (cffi.FFI.CData, bytes, int) -> None
    """
    Properly fix the index on a specific integer value of key. The key must
    be one of those the index has been endowed with.

    :param bytes key: the key to select
    :param int value: the value which has to be selected to use the index
    """
    codes_index_select_long = check_return(lib.codes_index_select_long)
    codes_index_select_long(indexid, key, value)


def codes_index_select_double(indexid, key, value):
    # type: (cffi.FFI.CData, bytes, float) -> None
    """
    Properly fix the index on a specific float value of key. The key must
    be one of those the index has been endowed with.

    :param bytes key: the key to select
    :param float value: the value which has to be selected to use the index
    """
    codes_index_select_double = check_return(lib.codes_index_select_double)
    codes_index_select_double(indexid, key, value)


def codes_index_select_string(indexid, key, value):
    # type: (cffi.FFI.CData, bytes, bytes) -> None
    """
    Properly fix the index on a specific string value of key. The key must
    be one of those the index has been endowed with.

    :param bytes key: the key to select
    :param bytes value: the value which has to be selected to use the index
    """
    codes_index_select_string = check_return(lib.codes_index_select_string)
    codes_index_select_string(indexid, key, value)


def codes_index_select(indexid, key, value):
    # type: (cffi.FFI.CData, bytes, T.Any) -> None
    """
    Select the message subset with key==value.

    :param indexid: id of an index created from a file.
        The index must have been created with the key in argument.
    :param bytes key: key to be selected
    :param bytes value: value of the key to select
    """
    if isinstance(value, int):
        codes_index_select_long(indexid, key, value)
    elif isinstance(value, float):
        codes_index_select_double(indexid, key, value)
    elif isinstance(value, bytes):
        codes_index_select_string(indexid, key, value)
    else:
        raise RuntimeError("Key value not recognised: %r %r (type %r)" % (key, value, type(value)))


_codes_get_size = check_return(lib.codes_get_size)


def codes_get_size(handle, key):
    # type: (cffi.FFI.CData, bytes) -> int
    """
    Get the number of coded value from a key.
    If several keys of the same name are present, the total sum is returned.

    :param bytes key: the keyword to get the size of

    :rtype: int
    """
    size = ffi.new('size_t *')
    _codes_get_size(handle, key, size)
    return size[0]


_codes_get_length = check_return(lib.codes_get_length)


def codes_get_length(handle, key):
    # type: (cffi.FFI.CData, bytes) -> int
    """
    Get the length of the string representation of the key.
    If several keys of the same name are present, the maximum length is returned.

    :param bytes key: the keyword to get the string representation size of.

    :rtype: int
    """
    size = ffi.new('size_t *')
    _codes_get_length(handle, key, size)
    return size[0]


_codes_get_bytes = check_return(lib.codes_get_bytes)


def codes_get_bytes_array(handle, key, size):
    # type: (cffi.FFI.CData, bytes, int) -> T.List[int]
    """
    Get unsigned chars array values from a key.

    :param bytes key: the keyword whose value(s) are to be extracted

    :rtype: List(int)
    """
    values = ffi.new('unsigned char[]', size)
    size_p = ffi.new('size_t *', size)
    _codes_get_bytes(handle, key, values, size_p)
    return list(values)


_codes_get_long_array = check_return(lib.codes_get_long_array)


def codes_get_long_array(handle, key, size):
    # type: (cffi.FFI.CData, bytes, int) -> T.List[int]
    """
    Get long array values from a key.

    :param bytes key: the keyword whose value(s) are to be extracted

    :rtype: List(int)
    """
    values = ffi.new('long[]', size)
    size_p = ffi.new('size_t *', size)
    _codes_get_long_array(handle, key, values, size_p)
    return list(values)


_codes_get_double_array = check_return(lib.codes_get_double_array)


def codes_get_double_array(handle, key, size):
    # type: (cffi.FFI.CData, bytes, int) -> T.List[float]
    """
    Get double array values from a key.

    :param bytes key: the keyword whose value(s) are to be extracted

    :rtype: T.List(float)
    """
    values = ffi.new('double[]', size)
    size_p = ffi.new('size_t *', size)
    _codes_get_double_array(handle, key, values, size_p)
    return list(values)


_codes_get_string_array = check_return(lib.codes_get_string_array)


def codes_get_string_array(handle, key, size, length=None):
    # type: (cffi.FFI.CData, bytes, int, int) -> T.List[bytes]
    """
    Get string array values from a key.

    :param bytes key: the keyword whose value(s) are to be extracted

    :rtype: T.List[bytes]
    """
    if length is None:
        length = codes_get_length(handle, key)
    values_keepalive = [ffi.new('char[]', length) for _ in range(size)]
    values = ffi.new('char*[]', values_keepalive)
    size_p = ffi.new('size_t *', size)
    _codes_get_string_array(handle, key, values, size_p)
    return [ffi.string(values[i]) for i in range(size_p[0])]


def codes_get_long(handle, key):
    # type: (cffi.FFI.CData, bytes) -> int
    value = ffi.new('long *')
    _codes_get_long = check_return(lib.codes_get_long)
    _codes_get_long(handle, key, value)
    return value[0]


def codes_get_double(handle, key):
    # type: (cffi.FFI.CData, bytes) -> int
    value = ffi.new('double *')
    _codes_get_long = check_return(lib.codes_get_double)
    _codes_get_long(handle, key, value)
    return value[0]


def codes_get_string(handle, key, length=None):
    # type: (cffi.FFI.CData, bytes, int) -> bytes
    """
    Get string element from a key.
    It may or may not fail in case there are more than one key in a message.
    Outputs the last element.

    :param bytes key: the keyword to select the value of
    :param bool strict: flag to select if the method should fail in case of
        more than one key in single message

    :rtype: bytes
    """
    if length is None:
        length = codes_get_length(handle, key)
    values = ffi.new('char[]', length)
    length_p = ffi.new('size_t *', length)
    _codes_get_string = check_return(lib.codes_get_string)
    _codes_get_string(handle, key, values, length_p)
    return ffi.string(values, length_p[0])


_codes_get_native_type = check_return(lib.codes_get_native_type)


def codes_get_native_type(handle, key):
    # type: (cffi.FFI.CData, bytes) -> int
    grib_type = ffi.new('int *')
    _codes_get_native_type(handle, key, grib_type)
    return grib_type[0]


def codes_get_array(handle, key, key_type=None,  size=None, length=None, log=LOG):
    # type: (cffi.FFI.CData, bytes, int, int, int, logging.Logger) -> T.Any
    if key_type is None:
        key_type = codes_get_native_type(handle, key)
    if size is None:
        size = codes_get_size(handle, key)

    if key_type == CODES_TYPE_LONG:
        return codes_get_long_array(handle, key, size)
    elif key_type == CODES_TYPE_DOUBLE:
        return codes_get_double_array(handle, key, size)
    elif key_type == CODES_TYPE_STRING:
        return codes_get_string_array(handle, key, size, length=length)
    elif key_type == CODES_TYPE_BYTES:
        return codes_get_bytes_array(handle, key, size)
    else:
        log.warning("Unknown GRIB key type: %r", key_type)


def codes_get(handle, key, key_type=None, length=None, log=LOG):
    # type: (cffi.FFI.CData, bytes, int, int, logging.Logger) -> T.Any
    if key_type is None:
        key_type = codes_get_native_type(handle, key)

    if key_type == CODES_TYPE_LONG:
        return codes_get_long(handle, key)
    elif key_type == CODES_TYPE_DOUBLE:
        return codes_get_double(handle, key)
    elif key_type == CODES_TYPE_STRING:
        return codes_get_string(handle, key, length=length)
    else:
        log.warning("Unknown GRIB key type: %r", key_type)


def codes_keys_iterator_new(handle, flags=CODES_KEYS_ITERATOR_ALL_KEYS, namespace=None):
    # type: (cffi.FFI.CData, int, bytes) -> cffi.FFI.CData
    if namespace is None:
        namespace = ffi.NULL

    codes_keys_iterator_new = lib.codes_keys_iterator_new
    return codes_keys_iterator_new(handle, flags, namespace)


def codes_keys_iterator_next(iterator_id):
    return lib.codes_keys_iterator_next(iterator_id)


def codes_keys_iterator_get_name(iterator):
    ret = lib.codes_keys_iterator_get_name(iterator)
    return ffi.string(ret)


def codes_keys_iterator_delete(iterator_id):
    codes_keys_iterator_delete = check_return(lib.codes_keys_iterator_delete)
    codes_keys_iterator_delete(iterator_id)


def codes_get_api_version():
    """
    Get the API version.

    Returns the version of the API as a string in the format "major.minor.revision".
    """
    ver = lib.codes_get_api_version()
    patch = ver % 100
    ver = ver // 100
    minor = ver % 100
    major = ver // 100

    return "%d.%d.%d" % (major, minor, patch)


def portable_handle_new_from_samples(samplename, product_kind):
    #
    # re-implement codes_grib_handle_new_from_samples in a portable way.
    # imports are here not to pollute the head of the file with (hopfully!) temporary stuff
    #
    import os.path
    import platform
    handle = ffi.NULL
    if platform.platform().startswith('Windows'):
        samples_folder = ffi.string(lib.codes_samples_path(ffi.NULL))
        sample_path = os.path.join(samples_folder, samplename + b'.tmpl')
        try:
            with open(sample_path) as file:
                handle = codes_handle_new_from_file(file, product_kind)
        except Exception:
            pass
    return handle


def codes_new_from_samples(samplename, product_kind=CODES_PRODUCT_GRIB):
    # type: (bytes, int) -> cffi.FFI.CData

    # work around an ecCodes bug on Windows, hopefully this will go away soon
    handle = portable_handle_new_from_samples(samplename, product_kind)
    if handle != ffi.NULL:
        return handle
    # end of work-around

    if product_kind == CODES_PRODUCT_GRIB:
        handle = lib.codes_grib_handle_new_from_samples(ffi.NULL, samplename)
    elif product_kind == CODES_PRODUCT_BUFR:
        handle = lib.codes_bufr_handle_new_from_samples(ffi.NULL, samplename)
    else:
        raise NotImplementedError("product kind not supported: %r" % product_kind)
    if handle == ffi.NULL:
        raise ValueError("sample not found: %r" % samplename)
    return handle


def codes_set_long(handle, key, value):
    # type: (cffi.FFI.CData, bytes, int) -> None
    codes_set_long = check_return(lib.codes_set_long)
    codes_set_long(handle, key, value)


def codes_set_double(handle, key, value):
    # type: (cffi.FFI.CData, bytes, float) -> None
    codes_set_double = check_return(lib.codes_set_double)
    codes_set_double(handle, key, value)


def codes_set_string(handle, key, value):
    # type: (cffi.FFI.CData, bytes, bytes) -> None
    size = ffi.new('size_t *', len(value))
    codes_set_string = check_return(lib.codes_set_string)
    codes_set_string(handle, key, value, size)


def codes_set(handle, key, value):
    """"""
    if isinstance(value, int):
        codes_set_long(handle, key, value)
    elif isinstance(value, float):
        codes_set_double(handle, key, value)
    elif isinstance(value, bytes):
        codes_set_string(handle, key, value)
    else:
        raise TypeError("Unsupported type %r" % type(value))


def codes_set_double_array(handle, key, values):
    # type: (cffi.FFI.CData, bytes, T.List[float]) -> None
    size = len(values)
    c_values = ffi.new("double []", values)
    codes_set_double_array = check_return(lib.codes_set_double_array)
    codes_set_double_array(handle, key, c_values, size)


def codes_set_long_array(handle, key, values):
    # type: (cffi.FFI.CData, bytes, T.List[int]) -> None
    size = len(values)
    c_values = ffi.new("long []", values)
    codes_set_long_array = check_return(lib.codes_set_long_array)
    codes_set_long_array(handle, key, c_values, size)


def codes_set_array(handle, key, values):
    # type: (cffi.FFI.CData, bytes, T.List[T.Any]) -> None
    if len(values) > 0:
        if isinstance(values[0], float):
            codes_set_double_array(handle, key, values)
        elif isinstance(values[0], int):
            codes_set_long_array(handle, key, values)
        else:
            raise TypeError("Unsupported value type: %r" % type(values[0]))
    else:
        raise ValueError("Cannot set an empty list.")


def codes_grib_multi_support_on(context=None):
    if context is None:
        context = ffi.NULL
    lib.codes_grib_multi_support_on(context)


def codes_grib_multi_support_off(context=None):
    if context is None:
        context = ffi.NULL
    lib.codes_grib_multi_support_off(context)


def codes_write(handle, outfile):
    # type: (cffi.FFI.CData, T.BinaryIO) -> None
    """
    Write a coded message to a file. If the file does not exist, it is created.

    :param str path: (optional) the path to the GRIB file;
        defaults to the one of the open index.
    """
    mess = ffi.new('const void **')
    mess_len = ffi.new('size_t*')
    codes_get_message = check_return(lib.codes_get_message)
    codes_get_message(handle, mess, mess_len)
    message = ffi.buffer(mess[0], size=mess_len[0])
    outfile.write(message)
