import enum
import inspect
import locale
import re

import typing
import sys
import os
import io
import uuid
import datetime


import base64
import configparser

import xml
import xml.etree
import xml.etree.ElementTree
import xml.dom
import xml.dom.minidom
import hashlib
import zlib

from enum import IntEnum, Enum
from typing import Any, List, Callable, Optional, Dict, Type, Union, Tuple

WX_IMPORTED = False
try:
    import wx
    WX_IMPORTED = True
except Exception as ex:
    print(f'wx Module not found {ex}')

PYMORHPY_IMPORTED = False
try:
    import pymorphy3
    PYMORHPY_IMPORTED = True
except Exception as ex:
    print(f'pymorphy module not found {ex}')

_morph = None
if PYMORHPY_IMPORTED:
    _morph:Optional[pymorphy3.MorphAnalyzer] = None

def normalize_words(word: str, number: int):
    if PYMORHPY_IMPORTED:
        words = word.split(' ')
        answ = []
        for s_word in words:
            if _morph:
                one = _morph.parse(s_word)[0]
                word_complete = one.make_agree_with_number(number)
                if word_complete:
                    answ.append(word_complete.word)
        return ' '.join(answ)
    else:
        return word




def normalize_str_to_path(src_str: str,utf_8: bool=False, replace_space:bool = False):
    #invalid =       r'<>:"/\|?*' for windows
    replacement: Dict[str, str] = {'<':'≤«',
                                   '>':'≥»',
                                   ':':'˸‡',
                                   '"':'”„',
                                   '/':'╱Ѓ', # '∕'
                                   '\\':'╲Њ',
                                   '|': '⏐¦',
                                   '?':'❓¶',
                                   '*':'☆•',
                                   ' ':'__'}
    if not replace_space:
        del replacement[' ']
    index = 1 if utf_8 else 0
    if src_str is None:
        return ''
    for char in replacement.keys():
        src_str = src_str.replace(char, replacement[char][index])
    return src_str

def extract_folders(path_str: str, depth: int):
    remaining = path_str
    if os.path.isabs(path_str):
        remaining = os.path.splitdrive(remaining)[1].lstrip(os.sep)
    parts = []
    while path_str:
        path_str, part = os.path.split(path_str)
        if part:
            parts.append(part)
        else:
            break
    selected = parts[-depth:] if depth<= len(parts) else parts
    selected.reverse()
    return os.path.join(*selected) if selected else "."

def extract_folder_get_count(path_str:str):
    return path_str.count(os.sep)+1

def extract_folder(path_str: str, level: int):
    remaining = path_str
    if os.path.isabs(path_str):
        remaining = os.path.splitdrive(remaining)[1].lstrip(os.sep)
    parts = []
    i: int = 0
    while path_str:
        path_str, part = os.path.split(path_str)
        if part:
            parts.append(part)
        else:
            break
        i+= 1
    parts.reverse()
    return parts[level] if 0<=level<len(parts)  else None


def check_is_path(src_str:str):
    invalid = r'<>:"/|?*'

    for i in invalid:
        if i in src_str:
            if i == ':' and src_str.count(':')==1 and src_str.index(':')==1:
                continue
            return False
    invalid_combinations = ['\\.', '.\\', '\\..', '..\\',]
    for i in invalid_combinations:
        if i in src_str:
            return False


    return True

def str_to_base64str(normal_str: str) -> str:
    try:
        b64_str = base64.b64encode(normal_str.encode("utf-8")).decode('utf-8')
        return f'{b64_str}'
    except Exception as ex:
        mlogger.error(f'str_to_base64 Ошибка преобразования строки {ex}')
    return ''

def base64str_to_str(base64_str: str)-> str:
    if len(base64_str)>0:
        try:
            b_array: bytes = base64.b64decode(base64_str)
            return str(b_array.decode("utf-8"))
        except Exception as ex:
            mlogger.error(f'base64_str Ошибка преобразования строки {ex}')
    return ''


def str_to_hash(input_str: str, hash_type:int, length:int=0)->str:
    hash_data = None
    if hash_type == 512:
        #return hashlib.sha512(input_str).hexdigest()
        hash_data = hashlib.sha512(input_str.encode('utf-8')) #.hexdigest()
    elif hash_type == 1:
        #return hashlib.sha512(input_str).hexdigest()
        hash_data = hashlib.sha1(input_str.encode('utf-8')) #.hexdigest()
    elif hash_type == 256:
        #return hashlib.sha512(input_str).hexdigest()
        hash_data = hashlib.sha256(input_str.encode('utf-8')) #.hexdigest()
    if hash_data:
        if length == 0:
            return hash_data.hexdigest()
        else:
            b64_hash = base64.b64encode(hash_data.digest()).decode()
            clean_hash = b64_hash.replace('/','#').rstrip('=')
            return clean_hash[:length]
    return ''



def str_to_crc32(input_str: str):
    return f'{zlib.crc32(input_str.encode('utf-8'),0):X}'

def crc32_file(file_name: str):
    prev = 0
    for eachLine in open(file_name, "rb"):
        prev = zlib.crc32(eachLine, prev)
    return f'{prev & 0xFFFFFFFF:X}'

def hash_file(filename:str, hash_type: int, buffsize:int=65536)->str:
    if not os.path.exists(filename):
        return ''
    """"This function returns the SHA-512 hash
    of the file passed into it"""

    # make a hash object
    h = None
    if hash_type == 512:
        h = hashlib.sha512()
    elif hash_type == 1:
        h = hashlib.sha512()
    elif hash_type == 256:
        h = hashlib.sha256()
    if not h:
        return ''
    # open file for reading in binary mode
    with open(filename,'rb') as file:

        # loop till the end of the file
        chunk = 0
        while chunk != b'':
            # read only 1024 bytes at a time
            chunk = file.read(buffsize)
            h.update(chunk)
    # return the hex representation of digest
    return h.hexdigest()

def get_run_path():
    return os.path.dirname(executable_file_name())

def executable_file_name():
    try:
        if hasattr(sys, '_MEIPASS') and hasattr(sys,'executable'):
            return sys.executable
        import __main__
        if hasattr(__main__, '__file__'):
            return __main__.__file__
    except Exception as ex1:
        sys.exit(f'Unable to get run path {ex1}')
    sys.exit('Unable to get run path')

default_notify_level = 100

# region Events
class EventType(IntEnum):
    ITEM_ADDED = 100
    ITEM_DELETED = 110
    ITEM_CHANGED = 130

    #ITEM_PROPERTY_CHANGED = 140

    ITEM_NEED_UPDATE = 200

    HISTORY_CHANGED = 300


    OPERATION_BEGIN = 800
    OPERATION_STEP = 805
    OPERATION_END = 810
    OPERATION_STEP_ERROR = 806



class EventObject:
    obj: Any
    old_obj: Any
    prop_name: str
    val: Any
    old_val: Any
    def __init__(self, obj: Any, old_obj: Any = None, prop_name:Optional[str]=None, val:Any=None, old_val:Any=None):
        self.obj = obj
        self.old_obj = old_obj
        self.prop_name = prop_name
        self.val = val
        self.old_val = old_val

class EventProgressObject:
    msg: Optional[str]
    max_val: Optional[int]
    cur_val: Optional[int]
    level: Optional[int]
    def __init__(self, msg: str='', cur_val: int = None, max_val:Optional[Union[int,float]]=None, level:int=default_notify_level):
        self.msg = msg
        self.max_val = max_val
        self.cur_val = cur_val
        self.level = level


class EventSubscriber:
    _listen: bool
    def __init__(self):
        self._listen = True

    def disable_listen(self):
        self._listen = False

    def enable_listen(self):
        self._listen = True

    @property
    def is_listening(self):
        return self._listen

    def on_notify(self, event_type: EventType, event_object: EventObject):
        if self._listen:
            if __debug__:
                if type(event_object) == EventObject:
                    obj = event_object.obj
                elif type(event_object) == EventProgressObject:
                    obj = event_object.msg
                mlogger.debug('N<= receiver={0} event={1} object={2} '.format(self.__class__.__name__, event_type.name, obj))



class EventPublisher:
    _subscribers: List[EventSubscriber]
    _should_notify: bool
    _callbacks: List[Callable[[EventType, EventObject],None]]
    _callbacks_params: Dict[Callable[[EventType, EventObject], None], Tuple[Any, Any]]
    def __init__(self):
        self._subscribers = []
        self._callbacks = []
        self._should_notify = True
        self._callbacks_params = {}

    def register_callback(self, callback_func: Callable[[EventType, EventObject],None], *args, **kwargs):
        self._callbacks.append(callback_func)
        self._callbacks_params[callback_func] = (args, kwargs)

    def unregister_callback(self, callback_func: Callable[[EventType, EventObject],None]):
        if callback_func in self._callbacks:
            self._callbacks.remove(callback_func)
            del self._callbacks_params[callback_func]

    def register_listener(self, subscriber: EventSubscriber):
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    def unregister_listener(self, subscriber: EventSubscriber):
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)

    def notify_listeners(self, event_type: EventType, event_object: Optional[Union[EventObject, EventProgressObject]]):
        if hasattr(self, '_should_notify'):
            if self._should_notify:
                if __debug__:
                    if type(event_object) == EventObject:
                        obj = event_object.obj
                    elif type(event_object) == EventProgressObject:
                        obj = event_object.msg
                    mlogger.debug('N=> sender={0} event={1} object={2}'.format(self.__class__.__name__, event_type.name, obj))
                for i in self._subscribers:
                    if i.is_listening:
                        i.on_notify(event_type, event_object)

                for callback in self._callbacks:
                    args, kwargs = self._callbacks_params[callback]
                    if args and kwargs:
                        callback(event_type, event_object, *args, **kwargs)
                    elif args and not kwargs:
                        callback(event_type, event_object, *args)
                    elif not args and not kwargs:
                        callback(event_type, event_object, **kwargs)
                    else:
                        callback(event_type, event_object)

    def _disable_notify(self):
        self._should_notify = False

    def _enable_notify(self):
        self._should_notify = True






# endregion

# region Logger
class LogLevel(IntEnum):
    ANY = 1000
    CRITICAL_ERROR = 10
    ERROR = 20
    WARNING = 30
    INFO = 40
    DEBUG_INFO = 45
    DEBUG = 50
    UNKNOWN = 100

class LogMessage:
    log_level: LogLevel
    msg: str
    time_stamp: datetime.datetime
    logger: 'Logger'

    def __init__(self, logger: 'Logger', log_level: LogLevel = -1, msg: Optional[str]="", dt: Optional[datetime.datetime] =None):
        self.logger = logger
        self.log_level = log_level
        self.msg = msg
        if dt is None:
            self.time_stamp = datetime.datetime.now()
        else:
            self.time_stamp = dt

class Logger:
    log_level: LogLevel
    logger_name: str
    msg_callbacks: List[Callable[[LogMessage], None]]
    use_history: bool
    history_messages: List[LogMessage]
    _notifier: EventPublisher
    _listener: EventSubscriber

    def __init__(self, log_level: LogLevel = LogLevel.ANY, use_history: bool = False, loger_name: str = ''):
        self.logger_name = loger_name
        self.log_level = log_level
        self.use_history = use_history
        self.history_messages = []
        self.msg_callbacks = []
        self._notifier = EventPublisher()
        self._listener = EventSubscriber()
        self._listener.on_notify = self._on_notifier_notify
        self._notifier.register_listener(self._listener)

    def get_notifier(self):
        return self._notifier

    def _on_notifier_notify(self, event_type: 'EventType', event_object: 'EventProgressObject'):
        if event_type == EventType.OPERATION_BEGIN:
            self.debug(f'Начало \"{event_object.msg}\" ({event_object.cur_val} из {event_object.max_val}) [{event_object.level}]')
        elif event_type == EventType.OPERATION_STEP:
            self.debug(f'Процесс \"{event_object.msg}\" ({event_object.cur_val} из {event_object.max_val}) [{event_object.level}]')
        elif event_type == EventType.OPERATION_END:
            self.debug(f'Завершено \"{event_object.msg}\" ({event_object.cur_val} из {event_object.max_val}) [{event_object.level}]')

    def add_message_callback(self, callback: Callable[[LogMessage], None]):
        self.msg_callbacks.append(callback)

    def delete_message_callback(self, callback: Callable[[LogMessage], None]):
        if callback in self.msg_callbacks:
            self.msg_callbacks.remove(callback)

    def critical_error(self, msg: str):
        new_msg = LogMessage(self, LogLevel.CRITICAL_ERROR, msg)
        if self.log_level >=LogLevel.CRITICAL_ERROR:
            if self.use_history:
                self.history_messages.append(new_msg)
            for callback in self.msg_callbacks:
                callback(new_msg)


    def error(self, msg: str):
        new_msg = LogMessage(self, LogLevel.ERROR, msg)
        if self.log_level >= LogLevel.ERROR:
            if self.use_history:
                self.history_messages.append(new_msg)
            for callback in self.msg_callbacks:
                callback(new_msg)

    def warning(self, msg: str):
        new_msg = LogMessage(self, LogLevel.WARNING, msg)
        if self.log_level >= LogLevel.WARNING:
            if self.use_history:
                self.history_messages.append(new_msg)
            for callback in self.msg_callbacks:
                callback(new_msg)

    def info(self, msg: str):
        new_msg = LogMessage(self, LogLevel.INFO, msg)
        if self.log_level >= LogLevel.INFO:
            if self.use_history:
                self.history_messages.append(new_msg)
            for callback in self.msg_callbacks:
                callback(new_msg)

    def debug_info(self, msg:str):
        new_msg = LogMessage(self, LogLevel.DEBUG_INFO, msg)
        if self.log_level >= LogLevel.DEBUG_INFO:
            if self.use_history:
                self.history_messages.append(new_msg)
            for callback in self.msg_callbacks:
                callback(new_msg)

    def debug(self, msg: str):
        new_msg = LogMessage(self, LogLevel.DEBUG, msg)
        if self.log_level >= LogLevel.DEBUG:
            if self.use_history:
                self.history_messages.append(new_msg)
            for callback in self.msg_callbacks:
                callback(new_msg)

    def send_unknown(self):
        new_msg = LogMessage(self, LogLevel.UNKNOWN, None)
        for callback in self.msg_callbacks:
            callback(new_msg)

# endregion
mlogger = Logger(LogLevel.ANY)

# region XMLStorable

class XMLStorableType(IntEnum):
    UNKNOWN = 0
    GENERIC = 1
    LIST = 2
    DICT = 3
    XMLSTORABLE = 4

class XMLStorable:
    """ типы должны быть определены в аннотациях не не должны содержать Optional, None и другую хрень """

    def load_from_str(self, src_str: str, use_base64: bool = False, clear: bool = False)->bool:
        if not src_str:
            mlogger.error('Строка src_str не содержит данных')
            return False
        if use_base64:
            src_str = base64str_to_str(src_str)
        if src_str:
            try:
                etree: xml.etree.ElementTree.Element = xml.etree.ElementTree.fromstring(src_str)
                if clear:
                    for key, val in self.__dict__.items():
                        self.__dict__[key] = None
                self._load_object(self, etree)
                return True
            except Exception as ex:
                mlogger.error(f'{self} ошибка преобразования строки {ex}')
                return False
        return False


    def save_to_str(self, use_base64: bool = False)->str:
        etree = xml.etree.ElementTree.Element('data')
        output_str = self._output(self._save_object(self, etree))
        if not use_base64:
            return output_str
        else:
            return str_to_base64str(output_str)


    def save_to_file(self, file_name: str):
        f = open(file_name, 'wt')
        f.write(self.save_to_str(False))
        f.close()

    def load_from_file(self, file_name: str):
        if os.path.exists(file_name):
            f = open(file_name, 'rt')
            file_str = f.read()
            f.close()
            self.load_from_str(file_str, False)


        else:
            mlogger.error('Файл {0} не найден'.format(file_name))

    @staticmethod
    def _dict_key_to_str(dict_key_type: Type, key: Any):
        if dict_key_type == str:
            return key
        elif dict_key_type == int:
            return str(key)
        elif dict_key_type == float:
            return str(key)
        elif dict_key_type == bool:
            return str(key)
        elif dict_key_type == datetime.datetime:
            k: datetime.datetime = key
            return k.isoformat()
        elif dict_key_type == datetime.date:
            k: datetime.date = key
            return k.isoformat()
        elif dict_key_type == uuid.UUID:
            k: uuid.UUID = key
            return str(k)
        elif inspect.isclass(dict_key_type):
            if dict_key_type.__class__.__module__ == 'enum':
                return key.name

        return None

    @staticmethod
    def _dict_key_from_str(dict_key_type: Type, key: Any):
        if dict_key_type == str:
            return key
        elif dict_key_type == int:
            return int(key)
        elif dict_key_type == float:
            return float(key)
        elif dict_key_type == bool:
            return bool(key)
        elif dict_key_type == datetime.datetime:
            k: datetime.datetime = datetime.datetime(1,1,1, 0,0,0)
            return k.fromisoformat(key)
        elif dict_key_type == datetime.date:
            k: datetime.date = datetime.date(1,1,1)
            return k.isoformat()
        elif dict_key_type == uuid.UUID:
            return uuid.UUID(key)
        elif inspect.isclass(dict_key_type):
            if dict_key_type.__class__.__module__ == 'enum':
                dict_key_type: Type[Enum]
                return dict_key_type[key]
        return None

    def _save_dict(self, dict_key_type: Type, dict_value_type: Type, values: Dict, parent_etree: xml.etree.ElementTree.Element):
        save_type = self._get_type(dict_value_type, False)
        for i, (key,val) in enumerate(values.items()):
            dict_key_name = self._dict_key_to_str(dict_key_type, key)
            sub_item = xml.etree.ElementTree.Element(f'item_{i}')
            sub_item.attrib['key'] = dict_key_name
            parent_etree.append(sub_item)
            if save_type == XMLStorableType.GENERIC:
                self._save_generic(dict_value_type, val, sub_item)
            elif save_type == XMLStorableType.XMLSTORABLE:
                self._save_object(val, sub_item)
            elif save_type == XMLStorableType.LIST:
                if val is not None:
                    sub_item.attrib['type'] = self._get_type(dict_value_type, True)
                    sub_item.attrib['count'] = str(len(val))
                    self._save_list(dict_value_type.__dict__['__args__'][0], val, sub_item)
            elif save_type == XMLStorableType.DICT:
                if val is not None:
                    sub_item.attrib['type'] = self._get_type(dict_value_type, True)
                    sub_item.attrib['key_type'] = dict_value_type.__dict__['__args__'][0].__name__
                    sub_item.attrib['count'] = str(len(val))
                    self._save_dict(dict_value_type.__dict__['__args__'][0], dict_value_type.__dict__['__args__'][1], val, sub_item)


    def _load_dict(self, dict_key_type: Type, dict_value_type: Type, parent_etree: xml.etree.ElementTree.Element):
        if 'count' not in parent_etree.attrib.keys():
            mlogger.error(f'В элементе {parent_etree} не найден атрибут count')
            return {}
        count = int(parent_etree.attrib['count'])
        answer_dict = {}
        load_type = self._get_type(dict_value_type, False)
        for i in range(count):
            row_item_name = f'item_{i}'
            row_item = parent_etree.find(row_item_name)
            if row_item is None:
                mlogger.error(f'Элемент {row_item_name} не найден в элементе {parent_etree}')
                continue
            key = self._dict_key_from_str(dict_key_type, row_item.attrib['key'])
            if key is None:
                row_item_attrib = row_item.attrib['key']
                mlogger.error(f'Элемент {row_item_name} содержит неверное наименование ключа \"{row_item_attrib}\"')
                continue

            if load_type == XMLStorableType.GENERIC:
                loaded_item = self._load_generic(row_item_name, dict_value_type, row_item)
                answer_dict[key] = loaded_item
            elif load_type == XMLStorableType.XMLSTORABLE:
                new_obj = dict_value_type()
                loaded_object = self._load_object(new_obj,row_item)
                answer_dict[key] = loaded_object
            elif load_type == XMLStorableType.LIST:
                loaded_list = self._load_list(dict_value_type.__dict__['__args__'][0],row_item)
                answer_dict[key] = loaded_list
            elif load_type == XMLStorableType.DICT:
                loaded_dict = self._load_dict(dict_value_type.__dict__['__args__'][0], dict_value_type.__dict__['__args__'][1],row_item)
                answer_dict[key] = loaded_dict
        return answer_dict


    def _save_list(self, list_type: Type, values: List, parent_etree: xml.etree.ElementTree.Element):
        save_type = self._get_type(list_type, False)
        for i, item in enumerate(values):
            titem = xml.etree.ElementTree.Element(f'item_{i}')
            parent_etree.append(titem)
            if save_type == XMLStorableType.GENERIC:
                self._save_generic(list_type, item, titem)
            elif save_type == XMLStorableType.XMLSTORABLE:
                self._save_object(item, titem)
            elif save_type == XMLStorableType.LIST:
                titem.attrib['type'] = self._get_type(list_type, True)
                titem.attrib['count'] = str(len(item))
                self._save_list(list_type.__dict__['__args__'][0], item, titem)
            elif save_type == XMLStorableType.DICT:
                titem.attrib['type'] = self._get_type(list_type, True)
                titem.attrib['key_type'] = list_type.__dict__['__args__'][0].__name__
                titem.attrib['count'] = str(len(item))
                self._save_dict(list_type.__dict__['__args__'][0], list_type.__dict__['__args__'][1], item, titem)


    def _load_list(self, list_type: Type, parent_etree: xml.etree.ElementTree.Element):
        if 'count' not in parent_etree.attrib.keys():
            mlogger.error(f'В элементе {parent_etree} не найден атрибут count')
            return []
        count = int(parent_etree.attrib['count'])
        output_list = []
        load_type = self._get_type(list_type, False)
        for i in range(count):
            row_item_name = f'item_{i}'
            row_item = parent_etree.find(row_item_name)
            if row_item is None:
                continue
            if load_type == XMLStorableType.GENERIC:
                loaded_item = self._load_generic(row_item_name, list_type, row_item)
                if loaded_item is not None:
                    output_list.append(loaded_item)
            elif load_type == XMLStorableType.XMLSTORABLE:
                new_obj = list_type()
                loaded_object = self._load_object(new_obj,row_item)
                if loaded_object is not None:
                    output_list.append(loaded_object)
            elif load_type == XMLStorableType.LIST:
                loaded_list = self._load_list(list_type.__dict__['__args__'][0],row_item)
                if loaded_list is not None:
                    output_list.append(loaded_list)
            elif load_type == XMLStorableType.DICT:
                loaded_dict = self._load_dict(list_type.__dict__['__args__'][0], list_type.__dict__['__args__'][1],row_item)
                if loaded_dict is not None:
                    output_list.append(loaded_dict)
        return output_list


    @staticmethod
    def _get_type(ttype: Type, as_string: bool)->Union[XMLStorableType,str]:
        if inspect.isclass(ttype):
            # может быть любой тип но не список или словарь, может быть другим XMLStorable
            if ttype.__module__ in ['builtins']:
                if as_string:
                    return ttype.__name__
                return XMLStorableType.GENERIC
            elif WX_IMPORTED and issubclass(ttype, (Enum, uuid.UUID, datetime.datetime, datetime.date, wx.Brush, wx.Pen, wx.Colour, wx.Font, wx.Size, configparser.ConfigParser)):
                if as_string:
                    return ttype.__name__
                return XMLStorableType.GENERIC
            elif not WX_IMPORTED and issubclass(ttype, (Enum, uuid.UUID, datetime.datetime, datetime.date, configparser.ConfigParser)):
                if as_string:
                    return ttype.__name__
                return XMLStorableType.GENERIC
            elif issubclass(ttype, XMLStorable):
                if as_string:
                    return 'XMLStorable'
                return XMLStorableType.XMLSTORABLE

        elif type(ttype) == typing._GenericAlias: # noqa
            if ttype.__dict__['__origin__'] == list:
                if as_string:
                    return 'list'
                return XMLStorableType.LIST
            elif ttype.__dict__['__origin__'] == dict:
                if as_string:
                    return 'dict'
                return XMLStorableType.DICT

        if as_string:
            return 'unknown'
        return XMLStorableType.UNKNOWN


    @staticmethod
    def _save_generic(prop_type: Type, value: Any, main_etree_item: xml.etree.ElementTree.Element):
        if value is None:
            main_etree_item.text = ''
            main_etree_item.attrib['none'] = 'True'
        else:
            main_etree_item.attrib['none'] = 'False'
            main_etree_item.attrib['type'] = str(prop_type.__name__)
            if prop_type is str:
                main_etree_item.text = value
            elif prop_type in [int, float]:
                main_etree_item.text = str(value)
            elif prop_type is bool:
                main_etree_item.text = 'True' if value else 'False'
            elif prop_type in [datetime.date, datetime.datetime]:
                src_val: datetime.date = value
                main_etree_item.text = src_val.isoformat()
            elif issubclass(prop_type, enum.Enum):
                src_val: enum.Enum = value
                main_etree_item.text = src_val.name
            elif issubclass(prop_type, configparser.ConfigParser):
                src_val: configparser.ConfigParser = value
                io_buffer = io.StringIO('')
                src_val.write(io_buffer)
                io_buffer.seek(0)
                main_etree_item.text = str_to_base64str(io_buffer.read())
            elif prop_type == uuid.UUID:
                src_val: enum.Enum = value
                main_etree_item.text = str(src_val)
            elif WX_IMPORTED:
                if prop_type == wx.Brush:
                    src_val: wx.Brush = value
                    src_color: wx.Colour = src_val.GetColour()
                    main_etree_item.text = f'{src_color.GetRGB()}|{src_val.GetStyle()}'
                elif prop_type == wx.Pen:
                    src_val: wx.Pen = value
                    src_color: wx.Colour = src_val.GetColour()
                    main_etree_item.text = f'{src_color.GetRGB()}|{src_val.GetWidth()}|{src_val.GetStyle()}'
                elif prop_type == wx.Colour:
                    src_color: wx.Colour = value
                    main_etree_item.text = f'{src_color.GetRGB()}'
                elif prop_type == wx.Font:
                    src_val: wx.Font = value
                    font_text = f'{src_val.GetFaceName()}' # строка
                    font_text += f'|{locale.str(src_val.GetPointSize())}' #integer
                    font_text += f'|{src_val.GetFamily()}' #integer
                    font_text += f'|{src_val.GetWeight()}' # integer
                    font_text += f'|{src_val.GetUnderlined()}' # bool
                    font_text += f'|{src_val.GetStrikethrough()}' #bool
                    font_text += f'|{src_val.GetEncoding()}' #integer
                    font_text += f'|{src_val.GetNativeFontInfo()}' #string ; splitted
                    main_etree_item.text = f'{src_val.GetNativeFontInfo()}'

                elif prop_type == wx.Size:
                    src_val: wx.Size = value
                    main_etree_item.text = f'{src_val.GetWidth()} {src_val.GetHeight()}'
            else:
                mlogger.error(f'Ошибка сохранения элемента {main_etree_item.tag} {prop_type} {value}')

    @staticmethod
    def _load_generic(prop_name: str, prop_type: Type, parent_etree: xml.etree.ElementTree.Element)->Any:

        if 'none' in parent_etree.attrib.keys():
            if parent_etree.attrib['none'] == 'True':
                return None
        if prop_type is str:
            return parent_etree.text
        elif prop_type in [int, float]:
            if prop_type == int:
                try:
                    return int(parent_etree.text)
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в int {ex1}')
                    return None
            elif prop_type == float:
                try:
                    return float(parent_etree.text)
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в float {ex1}')
                    return None
        elif prop_type is bool:
            if parent_etree.text == 'True':
                return True
            elif parent_etree.text == 'False':
                return False
            else:
                mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в bool')
                return None
        elif prop_type in [datetime.date, datetime.datetime]:
            if prop_type == datetime.date:
                try:
                    return datetime.date.fromisoformat(parent_etree.text)
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в float {ex1}')
                    return None
            elif prop_type == datetime.datetime:
                try:
                    return datetime.datetime.fromisoformat(parent_etree.text)
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в datetime {ex1}')
                    return None

        elif issubclass(prop_type, enum.Enum):
            try:
                return prop_type[parent_etree.text]
            except Exception as ex1:
                mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в Enum {ex1}')
                return None
        elif issubclass(prop_type, configparser.ConfigParser):
            try:
                cfg = configparser.ConfigParser()
                cfg_str = base64str_to_str(parent_etree.text)
                cfg.read_string(cfg_str)
                return cfg
            except Exception as ex1:
                mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в Enum {ex1}')
                return None

        elif prop_type == uuid.UUID:
            try:
                return uuid.UUID(parent_etree.text)
            except Exception as ex1:
                mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в Enum {ex1}')
                return None
        elif WX_IMPORTED:
            if prop_type == wx.Brush:
                try:
                    item_str = parent_etree.text.split('|')
                    return wx.Brush(wx.Colour(int(item_str[0])), int(item_str[1]))
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в wx.Brush {ex1}')
                    return None
            elif prop_type == wx.Pen:
                try:
                    item_str = parent_etree.text.split('|')
                    return wx.Pen(wx.Colour(int(item_str[0])), int(item_str[1]), int(item_str[2]))
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в wx.Pen {ex1}')
                    return None
            elif prop_type == wx.Colour:
                try:
                    item_str = parent_etree.text.split('|')
                    return wx.Colour(int(item_str[0]))
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в wx.Colour {ex1}')
                    return None
            elif prop_type == wx.Font:
                try:
                    new_font = wx.Font()
                    #face_name, point_size, family, style, weight, underlined, strikethrough, encoding, native_info = parent_etree.text.split('|')

                    #new_font.SetFaceName(face_name)
                    #new_font.SetPointSize(locale.atof(point_size))
                    new_font.SetNativeFontInfo(parent_etree.text)
                    return new_font
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в wx.Font {ex1}')
                    return None
            elif prop_type == wx.Size:
                try:
                    new_size = wx.Size()
                    width, height = parent_etree.text.split(' ')
                    new_size.SetWidth(locale.atoi(width))
                    new_size.SetHeight(locale.atoi(height))
                    return new_size
                except Exception as ex1:
                    mlogger.error(f'Ошибка преобразования {prop_name} {parent_etree.text} в wx.Size {ex1}')
                    return None
        else:
            mlogger.error(f'Ошибка загрузки элемента {prop_name} {prop_type} {parent_etree.text}')
        return None

    @staticmethod
    def _get_annotations(src_obj: Any):
        d: Dict[str, Type] = {}
        if not src_obj:
            return {}
        if not hasattr(src_obj.__class__,'mro'):
            return {}

        for c in src_obj.__class__.mro():
            try:
                if c == object:
                    break
                d.update(**c.__annotations__)
            except AttributeError:
                # object, at least, has no __annotations__ attribute.
                sys.exit(f'Object {c} of {src_obj} has no __annotations__ attribute')
        return d


    def _save_object(self, value: Any, parent_etree: xml.etree.ElementTree.Element):
        annotations = self._get_annotations(value)
        for prop_name, prop_type in annotations.items():
            if not hasattr(value, prop_name):
                mlogger.error(f'В объекте {value} экземпляр аттрибута \"{prop_name}\" не существует')
                continue
            titem = xml.etree.ElementTree.Element(prop_name)
            parent_etree.append(titem)
            save_type = self._get_type(prop_type, False)
            if save_type == XMLStorableType.GENERIC:
                titem.attrib['type'] = self._get_type(prop_type, True)
                generic_value = getattr(value, prop_name)
                self._save_generic(prop_type, generic_value, titem)
            elif save_type == XMLStorableType.XMLSTORABLE:
                titem.attrib['type'] = self._get_type(prop_type, True)
                self._save_object(getattr(value, prop_name), titem)
            elif save_type == XMLStorableType.DICT:
                titem.attrib['type'] = self._get_type(prop_type, True)
                titem.attrib['key_type'] = prop_type.__dict__['__args__'][0].__name__
                dict_values = getattr(value, prop_name)
                titem.attrib['count'] = str(len(dict_values))
                self._save_dict(prop_type.__dict__['__args__'][0], prop_type.__dict__['__args__'][1],dict_values, titem)
            elif save_type == XMLStorableType.LIST:
                titem.attrib['type'] = self._get_type(prop_type, True)
                list_values = getattr(value, prop_name)
                titem.attrib['count'] = str(len(list_values))
                self._save_list(prop_type.__dict__['__args__'][0], list_values, titem)
            else:
                mlogger.error(f'В объекте {value} аттрибута \"{prop_name}\" имеет неверный тип {save_type} {prop_type}')

        return parent_etree


    def _load_object(self,  value: Any, parent_etree: xml.etree.ElementTree.Element):
        annotations = self._get_annotations(value)
        for prop_name, prop_type in annotations.items():
            if not hasattr(value, prop_name):
                mlogger.error(f'В объекте {value} экземпляр аттрибута \"{prop_name}\" не существует')
                continue
            titem = parent_etree.find(prop_name)
            if titem is None:
                mlogger.error(f'В XML контейнере {parent_etree} дочерний элемент с именем \"{prop_name}\" не существует')
                continue
            if not hasattr(value, prop_name):
                mlogger.error(f'В объекте {value} экземпляр аттрибута \"{prop_name}\" не существует')
                continue
            load_type = self._get_type(prop_type, False)
            if load_type == XMLStorableType.GENERIC:
                loaded_object = self._load_generic(prop_name, prop_type, titem)
                if loaded_object is not None:
                    setattr(value, prop_name, loaded_object)
            elif load_type == XMLStorableType.XMLSTORABLE:
                tmp_obj = getattr(value, prop_name)
                if not tmp_obj:
                    tmp_obj = prop_type()
                loaded_object = self._load_object(tmp_obj, titem)
                if loaded_object is not None:
                    setattr(value, prop_name, loaded_object)
            elif load_type == XMLStorableType.LIST:
                loaded_list = self._load_list(prop_type.__dict__['__args__'][0], titem)
                if loaded_list:
                    setattr(value, prop_name, loaded_list)
            elif load_type == XMLStorableType.DICT:
                loaded_dict = self._load_dict(prop_type.__dict__['__args__'][0], prop_type.__dict__['__args__'][1], titem)
                if loaded_dict:
                    setattr(value, prop_name, loaded_dict)
            else:
                mlogger.error(f'В объекте {value} аттрибута \"{prop_name}\" имеет неверный тип {load_type} {prop_type}')

        return value




    @staticmethod
    def _output(element_item: xml.etree.ElementTree.Element) -> str:
        xml_str = xml.etree.ElementTree.tostring(element_item, encoding='utf8', method='xml')
        xml_dom_str = xml_str.decode('utf-8')
        dom = xml.dom.minidom.parseString(xml_dom_str)
        pretty_xml_as_string = dom.toprettyxml(encoding="utf-8")
        return pretty_xml_as_string.decode('utf-8')

#endregion



#region IniFile
class IniFile:
    _config: configparser.ConfigParser
    def __init__(self):
        self._config = configparser.ConfigParser()

    def save(self, file_name: str):
        try:
            f = open(file_name, 'w')
            self._config.write(f)
            f.close()
            return True
        except Exception as ex1:
            mlogger.error(f'ININ Ошибка сохранения файла {self._config} {file_name} {ex1}')
        return False

    def load(self, file_name: str):
        if os.path.exists(file_name):

            try:
                f = open(file_name, 'r')
                self._config.read_file(f)
                f.close()
                return True
            except Exception as ex1:
                mlogger.error(f'INI Ошибка сохранения файла {self._config} {file_name} {ex1}')
        return False

    def read_param_str(self, section, param)->Optional[str]:
        if self._config.has_section(section):
            if self._config.has_option(section, param):
                return self._config[section][param]
        return None

    def write_param_str(self, section, param, value)->bool:
        if type(section) != str or type(param)!=str or type(value)!=str:
            mlogger.error(f'INI значение параметров при записи должны быть строками')
            return False
        if not self._config.has_section(section):
            self._config.add_section(section)
        try:
            self._config[section][param] = value
            return True
        except Exception as ex1:
            mlogger.error(f'INI Ошибка записи параметра {ex1}')
        return False



#endregion

def config_parser_to_string(cfg: configparser.ConfigParser, use_base64: bool):
    io_buffer = io.StringIO('')
    cfg.write(io_buffer)
    io_buffer.seek(0)
    str_data = io_buffer.read()
    if use_base64:
        str_data = str_to_base64str(str_data)
    return str_data

def config_parser_from_string(src_str: str, use_base64:bool):

    cfg: configparser.ConfigParser = configparser.ConfigParser()
    if use_base64:
        src_str = base64str_to_str(src_str)
    cfg.read_string(src_str)
    return cfg

def get_config_parser_as_str(cfg: configparser.ConfigParser):
    with io.StringIO() as ss:
        cfg.write(ss)
        ss.seek(0)  # rewind
        return ss.read()
    return None
# endregion



class ValueType(IntEnum):
    """тип значения"""
    UNKNOWN = 0
    STRING = 1
    INT = 2
    FLOAT = 3
    BOOL = 4
    DATE = 5
    DATETIME = 6

    @staticmethod
    def to_str(val: 'ValueType'):
        if val == ValueType.UNKNOWN:
            return 'неизвестно'
        elif val == ValueType.STRING:
            return 'строка'
        elif val == ValueType.INT:
            return 'целое число'
        elif val == ValueType.FLOAT:
            return 'число с плавающей запятой'
        elif val == ValueType.BOOL:
            return 'двоичное значение'
        elif val == ValueType.DATE:
            return 'дата'
        elif val == ValueType.DATETIME:
            return 'дата и время'



_value_decimal_qualificators: Dict['ValueQualificator', Tuple[str, str, str]] = {}


class ValueQualificator(IntEnum):
    NONE =      0x000000000000  #||
    DECI =      0x000100000000  # д|деци|⁻¹
    SANTI =     0x000200000000  # с|санти|⁻²
    MILLI =     0x000300000000  # м|милли|⁻³
    MICRO =     0x000400000000  # мк|микро|⁻⁶
    NANO =      0x000500000000  # н|нано|⁻⁹
    PICO =      0x000600000000  # п|пико|⁻¹²
    FEMTO =     0x000700000000  # ф|фемто|⁻¹⁵
    ATTO =      0x000800000000  # а|атто|⁻¹⁸
    ZEPTO =     0x000900000000  # з|зепто|⁻²¹
    YOCTO =     0x000a00000000  # и|иокто|⁻²⁴
    RONTO =     0x000b00000000 # рн|ронто|⁻²⁷
    KVEKTO =    0x000c00000000  # кв|квекто|⁻³⁰
    DECA =      0x001000000000  # да|дека|¹
    HECTO =     0x002000000000  # г|гекто|²
    KILO =      0x003000000000  # к|кило|³
    MEGA =      0x004000000000  # М|мега|⁶
    GIGA =      0x005000000000  # Г|гига|⁹
    TERA =      0x006000000000  # Т|тера|¹²
    PETA =      0x007000000000  # П|пета|¹⁵
    EXA =       0x008000000000  # Э|экса|¹⁸
    ZETTA =     0x009000000000  # З|зетта|²¹
    YOTTA =     0x00a000000000  # И|йотта|²⁴
    RONNA =     0x00b000000000  # Рн|ронна|²⁷
    KVEKTA =    0x00c000000000  # Кв|кветта|³⁰

    @staticmethod
    def prefix(value_unit: 'ValueQualificator')->str:
        if value_unit in _value_decimal_qualificators.keys():
            return _value_decimal_qualificators[value_unit][0]
        return ''

    @staticmethod
    def description(value_unit: 'ValueQualificator'):
        if value_unit in _system_units.keys():
            return _value_decimal_qualificators[value_unit][1]
        return ''

    @staticmethod
    def postfix(value_unit: 'ValueQualificator') -> str:
        if value_unit in _system_units.keys():
            return _value_decimal_qualificators[value_unit][2]
        return ''


    @staticmethod
    def get_defined_types(um_type: 'MeasureUnit')->Optional[List['ValueQualificator']]:
        if um_type.is_bit_set(MeasureUnit.QUALIFICATOR):
            return [ValueQualificator.NONE,
                    ValueQualificator.DECI,
                    ValueQualificator.SANTI,
                    ValueQualificator.MILLI,
                    ValueQualificator.HECTO,
                    ValueQualificator.KILO,
                    ValueQualificator.MEGA]
        return [ValueQualificator.NONE]

_system_units: Dict['MeasureUnit', Tuple[str, str]] = {}

class MeasureUnit(IntEnum):
    # sub-superscript:⁰¹²³⁴⁵⁶⁷⁸⁹ ⁱ⁺⁻⁼⁽⁾ⁿ₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎
    # math: ×
    # arrows: ←↑→↓↔↕↖↗↘↙↚↛↜↝↞↟↠↡↢↣↤↥↦↧↨↩↪↫↬↭↮↯↰↱↲↳↴↵↶↷↸↹↺↻↼↽↾↿⇀⇁⇂⇃⇄⇅⇆⇇⇈⇉⇊⇋⇌⇍⇎⇏⇐⇑⇒⇓⇔⇕⇖⇗⇘⇙⇚⇛⇜⇝⇞⇟⇠⇡⇢⇣⇤⇥⇦⇧⇨⇩⇪⇫⇬⇭⇮⇯⇰⇱⇲⇳⇴⇵⇶⇷⇸⇹⇺⇻⇼⇽⇾⇿
    # text progress: ▁ ▂ ▃ ▄ ▅ ▆ ▇ █ ▉ thin: ▊ ▋ ▌ ▍ ▎ ▏ ▐ ░ ▒ ▓ ▔ ▕ ▖ ▗ ▘ ▙ ▚ ▛ ▜ ▝ ▞ ▟
    # icons: ☀☁☂☃☄★☆☇☈☉☊☋☌☍☎☏☐☑☒☓☔☕☖☗☘☙☚☛☜☝☞☟☠☡☢☣☤☥☦☧☨☩☪☫☬☭☮☯☰☱☲☳☴☵☶☷☸☹☺☻☼☽☾☿♀♁♂♃♄♅♆♇♈♉♊♋♌♍♎♏♐♑♒♓♔♕♖♗♘♙♚♛♜♝♞♟♠♡♢♣♤♥♦♧♨♩♪♫♬♭♮♯♰♱♲♳♴♵♶♷♸♹♺♻♼♽♾♿⚀⚁⚂⚃⚄⚅⚆⚇⚈⚉⚊⚋⚌⚍⚎⚏⚐⚑⚒⚓⚔⚕⚖⚗⚘⚙⚚⚛⚜⚝⚞⚟⚠⚡⚢⚣⚤⚥⚦⚧⚨⚩⚪⚫⚬⚭⚮⚯⚰⚱⚲⚳⚴⚵⚶⚷⚸⚹⚺⚻⚼⚽⚾⚿⛀⛁⛂⛃⛄⛅⛆⛇⛈⛉⛊⛋⛌⛍⛎⛏⛐⛑⛒⛓⛔⛕⛖⛗⛘⛙⛚⛛⛜⛝⛞⛟⛠⛡⛢⛣⛤⛥⛦⛧⛨⛩⛪⛫⛬⛭⛮⛯⛰⛱⛲⛳⛴⛵⛶⛷⛸⛹⛺⛻⛼⛽⛾⛿✀✁✂✃✄✅✆✇✈✉✊✋✌✍✎✏✐✑✒✓✔✕✖✗✘✙✚✛✜✝✞✟✠✡✢✣✤✥✦✧✨✩✪✫✬✭✮✯✰✱✲✳✴✵✶✷✸✹✺✻✼✽✾✿❀❁❂❃❄❅❆❇❈❉❊❋❌❍❎❏❐❑❒❓❔❕❖❗❘❙❚❛❜❝❞❟❠❡❢❣❤❥❦❧
    """единица измерения"""
    UNKNOWN =                               0xFFFFFFFF
    QUALIFICATOR =                               0x800000000000
    UNITLESS =                              0b0 # безразмерная величина
    SPACE =                                 0x1<<1 # пространство
    WEIGHT =                                0x1<<2 # масса
    TIME =                                  0x1<<3 # время
    CURRENT =                               0x1<<4 # сила тока
    TEMPERATURE =                           0x1<<5 # температура
    SUBSTANCE_NUMBER =                      0x1<<6 # количество вещества
    LIGHT_FORCE =                           0x1<<7 # сила света

    # производные займут два байта после
    BODY_ANGLE =                            0x100 | UNITLESS  # телесный угол
    ANGLE =                                 0x200 | UNITLESS  # угол
    COUNT =                                 0x300 | UNITLESS     # количество

    SQUARE =                                0x00100 | SPACE                                  # площадь
    VOLUME =                                0x00200 | SPACE                                  # объем
    LENGTH =                                0x00300 | SPACE                                  # длина
    SPEED =                                 0x00100 | SPACE | TIME                           # скорость
    ACCELERATION =                          0x00200 | SPACE | TIME                           # ускорение

    IMPULSE =                               0x00100 | WEIGHT | SPACE | TIME                  # импульс
    FORCE =                                 0x00200 | WEIGHT | SPACE | TIME                  # сила
    MECHANICAL_WORK =                       0x00300 | WEIGHT | SPACE | TIME                  # механическая работа
    ENERGY =                                0x00400 | WEIGHT | SPACE | TIME                  # энергия
    POWER =                                 0x00500 | WEIGHT | SPACE | TIME                  # мощность
    PRESSURE =                              0x00600 | WEIGHT | SPACE | TIME                  # давление
    QUANTITY_OF_HEAT =                      0x00700 | WEIGHT | SPACE | TIME                  # количество теплоты
    MOMENT_OF_FORCE =                       0x00800 | WEIGHT | SPACE | TIME                  # момент силы
    MOMENT_OF_IMPULSE =                     0x00900 | WEIGHT | SPACE | TIME                  # момент импульса

    DENSITY =                               0x00100 | WEIGHT | SPACE                         # плотность
    SPACE_DENSITY =                         0x00200 | WEIGHT | SPACE                         # поверхностная плотность
    LINEAR_DENSITY =                        0x00300 | WEIGHT | SPACE                         # линейная плотность
    MOMENT_OF_INERTIA =                     0x00400 | WEIGHT | SPACE                         # момент инерции

    ELECTRIC_CHARGE =                       0x00100 | CURRENT | TIME                         # электрический заряд

    VOLTAGE =                               0x00100 | SPACE | WEIGHT | TIME | CURRENT        # напряжение
    ELECTRIC_RESISTANCE =                   0x00200 | SPACE | WEIGHT | TIME | CURRENT        # сопротивление
    ELECTRIC_CAPACITY =                     0x00300 | SPACE | WEIGHT | TIME | CURRENT        # электроемкость
    ELECTRIC_CONDUCTIVITY =                 0x00400 | SPACE | WEIGHT | TIME | CURRENT        # проводимость

    MAGNETIC_FLOW =                         0x00100 | SPACE | WEIGHT | TIME | CURRENT        # магнитный поток
    MAGNETIC_INDUCTIVITY =                  0x00200 | SPACE | WEIGHT | TIME | CURRENT        # индуктивность

    FREQUENCY =                             0x00100 | TIME                                   # частота
    ANGLE_SPEED =                           0x00200 | TIME                                   # угловая скорость
    ANGLE_ACCELERATION =                    0x00300 | TIME                                   # угловое ускорение

    RADIOACTIVE_ACTIVITY =                  0x00100 | TIME                                   # активность катализатора
    RADIOACTIVE_ABSORBED_IONIZATION_DOSE=   0x00100 | SPACE | TIME                           # поглащенная доза ионизирующего изулчения
    RADIOACTIVE_IONIZATION_DOSE =           0x00200 | SPACE | TIME                           # эквивалентная доза ионизирующего излучения

    ILLUMINATION =                          0x00100 | LIGHT_FORCE                            #освещенность
    LIGHT_FLOW  =                           0x00200 | LIGHT_FORCE                            #световой поток



    # на наименование типа выделено три байта, на единицу измерения выделено еще три байта и два байта выделено на размерность величины

    # на непосредственные единицы измерения выделено еще два байта

    UNITLESS_UNIT =                         0x000000100000 | UNITLESS                 # ед.|единица
    UNITLESS_COUNT =                        0x000000200000 | UNITLESS                 # шт.|штука
    UNITLESS_NOTHING =                      0x000000300000 | UNITLESS                 # -|-

    LENGTH_m =                              0x000000100000 | LENGTH | QUALIFICATOR    # м|метр

    PRESSURE_PASCAL =                       0x000000100000 | PRESSURE | QUALIFICATOR  # Па|Паскаль
    PRESSURE_ATM =                          0x000000200000 | PRESSURE | QUALIFICATOR  # атм|атмосфера


    @staticmethod
    def to_str(value_unit: 'MeasureUnit')->str:
        if value_unit in _system_units.keys():
            return _system_units[value_unit][0]
        return ''

    @staticmethod
    def description(value_unit: 'MeasureUnit'):
        if value_unit in _system_units.keys():
            return _system_units[value_unit][1]
        return ''

    @staticmethod
    def get_defined_types():
        return list(_system_units.keys())


    def is_bit_set(self, bit: 'MeasureUnit'):
        if self.value & bit == bit:
            return True
        return False

_unit_short_names: Dict[str, Tuple[ValueQualificator, MeasureUnit]] = {}
_unit_descr_names: Dict[str, Tuple[ValueQualificator, MeasureUnit]] = {}


def get_unit_by_name(search_str:str)->Optional[Tuple[ValueQualificator, MeasureUnit]]:
    if search_str in _unit_short_names:
        return _unit_short_names[search_str]
    return None

def get_unit_by_description(search_str: str)->Optional[Tuple[ValueQualificator, MeasureUnit]]:
    if search_str in _unit_descr_names:
        return _unit_descr_names[search_str]
    return None

# секция инициализации модуля


module_name =os.path.splitext(os.path.basename(__file__))[0] if len(os.path.splitext(os.path.basename(__file__))) else None
if __name__ == module_name:
    _morph = pymorphy3.MorphAnalyzer(lang='ru')
    reg_expression = re.compile('\\s+(\\S+)\\s*=.+#\\s*(.+)\\s*\\|\\s*(.+)\\s*\\|\\s*(.+)\\s*')  # ValueDecimalQualificator
    _value_decimal_qualificators[ValueQualificator.NONE] = '', '', ''
    each_line = inspect.getsource(ValueQualificator).split('\n')
    for line in each_line:
        match = reg_expression.search(line)
        if match:
            var_name = match.group(1)
            prefix_str = match.group(2)
            descr_str = match.group(3)
            postfix_str = match.group(2)
            if var_name in ValueQualificator.__dict__.keys():
                new = ValueQualificator[var_name]
                _value_decimal_qualificators[new] = prefix_str, descr_str, postfix_str


    reg_expression = re.compile('\\s+(\\S+)\\s*=.+#\\s*(.+)\\s*\\|\\s*(.+)\\s*')  # MeasureUnits
    each_line = inspect.getsource(MeasureUnit).split('\n')
    _system_units[MeasureUnit.UNKNOWN] = '', ''
    for line in each_line:
        match = reg_expression.search(line)
        if match:
            var_name = match.group(1)
            str_str = match.group(2)
            descr_str = match.group(3)
            if var_name in MeasureUnit.__dict__.keys():
                new = MeasureUnit[var_name]
                _system_units[new] = str_str, descr_str

    for u_type in MeasureUnit.get_defined_types():
        if u_type in _system_units.keys():
            name = _system_units[u_type][0]
            descr = _system_units[u_type][1]
            q_types = ValueQualificator.get_defined_types(u_type)
            for q_type in q_types:
                name = _value_decimal_qualificators[q_type][0]+name
                _unit_short_names[name] = q_type, u_type
                descr = _value_decimal_qualificators[q_type][1]+descr
                _unit_descr_names[descr] = q_type, u_type


def get_doctring(source_class: Type, source_variable_name: str):
    source = inspect.getsource(source_class)
    lines = source.split('\n')
    for i, line in enumerate(lines):
        if re.match(rf'^\s*{source_variable_name}\s*[:=]',line):
            next_line  = lines[i+1].strip() if i+1<len(lines) else None
            next_line = next_line.lstrip('"""').rstrip('"""').lstrip(' ').rstrip(' ')
            return next_line
    return None


class AnnotationReader:
    @staticmethod
    def get_class_info(module, code_str: str):
        pattern = r'class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([\s\S]*?)\))?\s*:'
        matches = re.findall(pattern, code_str)
        class_name = ''
        parents = []
        for match in matches:
            class_name = match[0]
            parent_str = match[1]
            if parent_str:
                parent_str = re.sub(r'#.*', '', parent_str)
                parent_str = parent_str.replace('\n', ' ')
                parents = [p.strip() for p in re.split(r'\s*,\s*', parent_str) if p.strip()]
            else:
                parents = []
        if class_name:
            if hasattr(module, class_name):
                return getattr(module, class_name)
        return None

    @staticmethod
    def get_intenum_annotations(code_str: str):
        """Parse IntEnum class to extract constants with values, comments and docstrings"""
        # Компактное регулярное выражение в одну строку
        pattern = r'^\s*(?P<name>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>\d+)\s*(?:#\s*(?P<comment>.*?)\s*$)?(?:\s*\"\"\"\s*(?P<docstring>.*?)\s*\"\"\"\s*$)?'
        matches = re.finditer(pattern, code_str, re.MULTILINE)
        results = []
        for m in matches:
            results.append((m.group('name'),int(m.group('value')),m.group('docstring').strip() if m.group('docstring') else None, m.group('comment') if m.group('comment') else None,))
        return results
