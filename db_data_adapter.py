
import math


import win32com
import win32com.client

import basic

WX_IMPORTED = False

try:
    import wx
    WX_IMPORTED = True
except Exception as ex1:
    print(f'wx Module not found {ex1}')


import configparser
import datetime
import inspect
import os.path
import sqlite3
import sys
import typing
import uuid
from enum import IntEnum, Enum
from typing import List, Optional, Dict, Type, Tuple, Any, Union

import pyodbc


from basic import EventPublisher, EventSubscriber, Logger, EventType, EventObject, EventProgressObject



class PropertyType(IntEnum):
    UNKNOWN = 0
    GENERIC = 1
    ENUM = 2
    CLASS_INSTANCE = 3
    LIST_SPLITTED = 5


class DBStorableRow(EventPublisher):
    _guid: Optional[uuid.UUID]
    _table: Optional['DBStorableTable']

    def __init__(self, parent: Optional['DBStorableTable']=None):
        EventPublisher.__init__(self)
        #self.__db_storable_items = {}
        self._guid = None
        self._table = parent


    @property
    def table(self):
        return self._table

    @table.setter
    def table(self, val):
        self._table = val

    @property
    def guid(self)->Optional[uuid.UUID]:
        return self._guid

    def set_guid(self, guid:uuid.UUID):
        self._guid = guid

    def new_guid(self,index: Optional[int] =None):
        if self._guid is None:
            if index is None:
                self._guid = uuid.uuid4()
            else:
                self._guid = uuid.UUID(int=index)

    #def write(self, old_item: Optional['DBStorableRow']=None):
    #    self.notify_listeners(EventType.ITEM_CHANGED,EventObject(self, old_obj=old_item))

    @classmethod
    def get_properties(cls)->Dict[str, Tuple[PropertyType, Type]]:
        answ: Dict[str, Tuple[PropertyType, Type]] = {}
        for c in cls.mro():
            if hasattr(c, '__annotations__'):
                for prop_name in c.__annotations__.keys():
                    if not prop_name.startswith('_') or prop_name == '_guid':
                        answ[prop_name] = cls.get_property_type(c.__annotations__[prop_name])
        return answ

    @staticmethod
    def remove_optional(prop: Type) -> Type:
        if hasattr(prop, '__args__'):
            if len(prop.__args__) == 2:
                prop = prop.__args__[0]
        return prop

    @classmethod
    def get_property_type(cls, prop: Type) -> Tuple[PropertyType, Type]:
        prop = cls.remove_optional(prop)

        if type(prop) == typing.ForwardRef:
            # noinspection PyUnresolvedReferences
            class_name = prop.__forward_arg__  # это имя класса который должен существовать но не определен в аннотациях
            if cls.__module__ in sys.modules.keys():
                if hasattr(sys.modules[cls.__module__], class_name):
                    prop = getattr(sys.modules[cls.__module__], class_name)

        if inspect.isclass(prop):
            # может быть любой тип, но не список или словарь, может быть другим XMLStorable
            if prop.__module__ in ['builtins']:
                return PropertyType.GENERIC, prop
            elif WX_IMPORTED and issubclass(prop, (uuid.UUID, datetime.datetime, datetime.date, wx.Brush, wx.Pen, wx.Colour, wx.Font, configparser.ConfigParser)):
                return PropertyType.GENERIC, prop
            elif not WX_IMPORTED and issubclass(prop, (uuid.UUID, datetime.datetime, datetime.date, configparser.ConfigParser)):
                return PropertyType.GENERIC, prop
            elif issubclass(prop, Enum):
                return PropertyType.ENUM, prop
            elif issubclass(prop, DBStorableRow):
                return PropertyType.CLASS_INSTANCE, prop

        # noinspection PyUnresolvedReferences
        if type(prop).__name__ == '_GenericAlias':
            if hasattr(prop, '__args__'):
                if len(prop.__args__) == 1:
                    prop = cls.remove_optional(prop.__args__[0])
                    if type(prop) == typing.ForwardRef:
                        return PropertyType.LIST_SPLITTED, cls.get_property_type(prop)[1]
                    else:
                        return PropertyType.LIST_SPLITTED, prop
        return PropertyType.UNKNOWN, prop


    def copy(self):
        new_item = type(self)(self.table)
        new_item.set_guid(self.guid)
        self.save(new_item, True, False)
        return new_item

    def save(self, save_obj: 'DBStorableRow', write_non_existing: bool, no_set_if_wrong_type: bool, skip_guid: bool = False):
        """сохранение текущего объекта в save_obj"""
        if save_obj is None:
            self.table.dataset.logger.error(f'{self} {self.guid} невозможно сохранить в пустой объект')
            return

        if not issubclass(type(save_obj), DBStorableRow):
            self.table.dataset.logger.error(f'{self} {self.guid} невозможно сохранить в объект {save_obj}, разные типы')
            return


        for prop_name, (prop_type, p_type) in self.get_properties().items():
            if skip_guid and prop_name == '_guid':
                continue
            if not hasattr(self, prop_name):
                if write_non_existing:
                    setattr(save_obj, prop_name, None)
                else:
                    continue

            src_val = getattr(self, prop_name, None)
            if not hasattr(save_obj, prop_name) and not write_non_existing:
                continue

            if prop_type in [PropertyType.GENERIC, PropertyType.ENUM]: # если это простое значение
                if src_val is None or type(src_val) == p_type:
                    setattr(save_obj, prop_name, src_val)
                else:
                    if type(src_val)!= p_type and no_set_if_wrong_type:
                        self.table.dataset.logger.debug(f'{self} свойство {prop_name} тип {prop_type} не установлено, по условию пропуска несоответствия типов')
                    else:
                        self.table.dataset.logger.error(f'{self} свойство {prop_name} тип {prop_type}: исходное значение {type(src_val)} не соответствует типу {p_type}')

            elif prop_type == PropertyType.CLASS_INSTANCE:
                if src_val is None or type(src_val) == p_type:
                    setattr(save_obj, prop_name, src_val)
                else:
                    if type(src_val)!= p_type and no_set_if_wrong_type:
                        self.table.dataset.logger.debug(f'{self} свойство {prop_name} тип {prop_type} не установлено, по условию пропуска несоответствия типов')
                    else:
                        self.table.dataset.logger.error(f'{self} свойство {prop_name} тип {prop_type}: объект {src_val} не соответствует типу {p_type}')
            elif prop_type == PropertyType.LIST_SPLITTED:
                src_list: List[Any] = getattr(self, prop_name)
                dst_list: List[Any] = getattr(save_obj, prop_name, None)
                if src_list is dst_list:
                    continue
                if not (type(src_list) == list or src_list is None):
                    self.table.dataset.logger.error(f'{self} свойство {prop_name} тип {prop_type}: исходный список имеет неверный тип {type(src_list)}')
                    continue
                if type(src_list) == list:
                    src_list: List[Any]
                    if type(dst_list) != list:
                        if no_set_if_wrong_type:
                            self.table.dataset.logger.debug(f'{self} свойство {prop_name} тип {prop_type} не установлено, по условию пропуска несоответствия типов')
                            continue
                        dst_list = []
                    dst_list.clear()
                    for item in src_list:
                        dst_list.append(item)
                    setattr(save_obj, prop_name, dst_list)
                else:
                    if type(dst_list) == list or dst_list is None:
                        setattr(save_obj, prop_name, None)
                    else:
                        if no_set_if_wrong_type:
                            self.table.dataset.logger.error(f'{self} свойство {prop_name} тип {prop_type} для объекта {save_obj} не установлено, по условию пропуска несоответствия типов')
                            continue
                        else:
                            setattr(save_obj, prop_name, None)

            else:
                self.table.dataset.logger.error(f'{self} свойство {prop_name} не имеет обработчика для типа {prop_type}')


    def clear(self):
        for prop_name, (prop_type, p_type) in self.get_properties().items():
            if hasattr(self, prop_name):
                if not prop_type in [PropertyType.CLASS_INSTANCE, PropertyType.LIST_SPLITTED]:
                    setattr(self, prop_name, None)
                elif prop_type == PropertyType.CLASS_INSTANCE:
                    class_item: DBStorableRow = getattr(self,prop_name)
                    if class_item is not None:
                        if issubclass(type(class_item), DBStorableRow):
                            class_item.clear()
                        else:
                            self.table.dataset.logger.error(f'{self} свойство {prop_name} тип {prop_type}: не является классом DBStorableRow')
                elif prop_type == PropertyType.LIST_SPLITTED:
                    src_list_obj: List[Any] = getattr(self, prop_name)
                    if type(src_list_obj) == list:
                        src_list_obj.clear()
                    else:
                        self.table.dataset.logger.error(f'{self} свойство {prop_name} тип {prop_type}: {src_list_obj} не является списком')
                else:
                    self.table.dataset.logger.error(f'{self} свойство {prop_name} тип {prop_type}: неизвестный тип объекта для сохранения')
            else:
                self.table.dataset.logger.error(f'{self} свойство {prop_name} тип {prop_type}: не имеет свойства для сохранения')


class DBAdapterRow:
    table_name: str
    fields: Dict[str, Any]
    field_types: Dict[str, Type]
    guid: Optional[uuid.UUID]
    def __init__(self):
        self.fields = {}
        self.field_types = {}
        self.table_name = ''
        self.guid = None


class DBFindRule(Enum):
    EQUAL = 0
    GREATER_OR_EQUAL = 1
    LOWER_OR_EQUAL = 2
    GREATER = 3
    LOWER = 4
    NOT_EQUAL = 5
    BETWEEN = 6
    BETWEEN_INCLUDE = 7
    LIST = 8
    EQUAL_OR_NULL = 10
    GREATER_OR_EQUAL_OR_NULL = 11
    LOWER_OR_EQUAL_OR_NULL = 12
    GREATER_OR_NULL = 13
    LOWER_OR_NULL = 14
    NOT_EQUAL_OR_NULL = 15

    """Список полей из другой таблицы """


class DBStorableTable(EventPublisher, EventSubscriber):
    _items: Dict[uuid.UUID, Union[DBStorableRow, List[DBStorableRow]]]
    _item_states: Dict[uuid.UUID, DBStorableRow]

    _table_type: Type[DBStorableRow]

    _name: str
    _data_adapter: Optional['DBAdapter']
    _dataset: 'DBStorableDataset'

    _history: List[Tuple[EventType, uuid.UUID, DBStorableRow, Optional[DBStorableRow]]]

    _history_pointer: int

    _instant_save: bool
    _table_loading: bool
    _item_count: int

    def __init__(self, parent: 'DBStorableDataset', name: str, instant_save: bool, data_adapter: 'DBAdapter'):  # , parent_dataset: DBStorableDataset):
        EventPublisher.__init__(self)
        EventSubscriber.__init__(self)
        self._items = {}
        self._item_states = {}
        self._name = name
        self._data_adapter = data_adapter
        self._dataset = parent
        self._history = []
        self._history_pointer = -1
        self._instant_save = instant_save
        self._table_loading = False
        self._item_count = 0

    @property
    def table_loading(self):
        return self._table_loading

    @property
    def data_adapter(self):
        return self._data_adapter

    @property
    def dataset(self):
        return self._dataset

    @property
    def table_type(self) -> Type[DBStorableRow]:
        return self._table_type

    @table_type.setter
    def table_type(self, val: Type[DBStorableRow]):
        self._table_type = val

    @property
    def name(self):
        return self._name

    @property
    def instant_save(self):
        return self._instant_save

    #@instant_save.setter
    #def instant_save(self, val: bool):
    #    self._instant_save = val

    @property
    def items_count(self):
        return len(self._items)

    def add(self, item: DBStorableRow, use_history: bool, save_to_db:bool) -> bool:
        if item.guid is None:
            item.new_guid()
        if item.guid not in self._items.keys():
            item.table = self
            item.register_listener(self)
            self._items[item.guid] = item
            self._item_states[item.guid] = item.copy()
            self._item_count += 1
            #for p_name, (p_type, p_sub_type) in self._item_states[item.guid].get_properties().items():
            #    if p_type in [PropertyType.LIST_SPLITTED, PropertyType.ENUM]:
            #        val = getattr(item,p_name,None)
            #        new_val = copy.copy(val)
            #        print(f'{id(val)} {id(new_val)}')
            #        setattr(self._item_states[item.guid], p_name, new_val)

            evt_obj = EventObject(item)
            history_item = EventType.ITEM_ADDED, item.guid, item, None
            if use_history and save_to_db:
                del self._history[self._history_pointer + 1:]
                self._history.append(history_item)
                self._history_pointer += 1

            if self._instant_save or (not use_history and save_to_db):
                if save_to_db and self._data_adapter:
                    self._save_to_db(history_item)
                    if use_history:
                        self.history_clear()

            self.notify_listeners(EventType.ITEM_ADDED, evt_obj)

            return True
        return False

    def write(self, item: DBStorableRow, use_history: bool, save_to_db: bool) -> bool:
        if item.guid is None:
            self.dataset.logger.error(f'{self} невозможно записать объект {item} с guid=None')
            return False
        if item.guid in self._items.keys() and item.guid in self._item_states.keys():
            old_item = self._item_states[item.guid].copy()
            new_item = self.get(item.guid)
            item.save(self._items[item.guid], False, True)
            #.load_from(item)
            item.save(self._item_states[item.guid], False, True)
            #self._item_states[item.guid].load_from(item)


            evt_obj = EventObject(new_item, old_item)
            history_item = EventType.ITEM_CHANGED, item.guid, new_item.copy(), old_item
            if use_history and save_to_db:
                del self._history[self._history_pointer + 1:]
                self._history.append(history_item)
                self._history_pointer += 1
            if self._instant_save or (not use_history and save_to_db):
                if save_to_db and self._data_adapter:
                    self._save_to_db(history_item)
                    if use_history:
                        self.history_clear()
            self.notify_listeners(EventType.ITEM_CHANGED, evt_obj)
            return True
        return False



    def delete(self, item: DBStorableRow, use_history: bool, save_to_db: bool) -> bool:
        if item.guid is None:
            self.dataset.logger.error(f'{self} невозможно удалить объект {item} с guid=None')
            return False

        if item.guid in self._items.keys():
            item.unregister_listener(self)

            evt_obj = EventObject(self._items[item.guid])
            history_item = EventType.ITEM_DELETED, item.guid, self._items[item.guid], None

            del self._items[item.guid]
            del self._item_states[item.guid]
            self._item_count -= 1
            if use_history and save_to_db:
                del self._history[self._history_pointer + 1:]
                self._history.append(history_item)
                self._history_pointer += 1
            if self._instant_save or (not use_history and save_to_db):
                if save_to_db and self._data_adapter:
                    self._save_to_db(history_item)
                    if use_history:
                        self.history_clear()
            self.notify_listeners(EventType.ITEM_DELETED, evt_obj)
            return True
        return False



    @property
    def count(self):
        return self._item_count

    def on_notify(self, event_type: EventType, event_object: EventObject):
        EventSubscriber.on_notify(self, event_type, event_object)
        # если объект был изменен
        #if event_type == EventType.ITEM_CHANGED:
        #    changed_row: DBStorableRow = copy.copy(event_object.obj)
        #    del self._history[self._history_pointer + 1:]
        #    history_item = event_type, changed_row.guid, copy.copy(self._item_states[changed_row.guid]), changed_row
        #    self._history.append(history_item)
        #    self._history_pointer = len(self._history) - 1
        #    if self._instant_save:
        #        self._save_to_db(history_item)
        #        self.history_clear()
        #    self._item_states[changed_row.guid].load_from(changed_row)
        #    self.notify_listeners(event_type, event_object)
        pass


    def clear(self):
        self._items.clear()
        self._item_states.clear()


    def get(self, guid: uuid.UUID) -> Optional[Union[DBStorableRow, List[DBStorableRow]]]:
        if guid in self._items.keys():
            item = self._items[guid]
            return item
        return None

    def get_items(self):
        return self._items.values()


    def find_items(self, search_rules: List[Tuple[str, Any, DBFindRule]])->List[DBStorableRow]:
        answer = []
        field_names = [search_rule[0] for search_rule in search_rules]
        db_field_names = [key for key in self.table_type.get_properties().keys()]
        for field_name in field_names:
            if field_name not in db_field_names:
                self.dataset.logger.error(f'({self.name}) При выполнении функции поиска в таблице {self.name} поле поиска "{field_name}" не найдено среди возможных полей {list(self.table_type.get_properties().keys())}')
                return answer
        #[search_field: str, value: Any, seek_rule: DBFindRule]


        for item in self.get_items():
            all_items_found = True
            for search_rule in search_rules:
                search_field = search_rule[0]
                value = search_rule[1]
                seek_rule = search_rule[2]
                val = getattr(item, search_field)
                if seek_rule == DBFindRule.EQUAL:
                    if val == value:
                        continue
                elif seek_rule == DBFindRule.NOT_EQUAL:
                    if val != value:
                        continue
                elif seek_rule == DBFindRule.LOWER:
                    if val < value:
                        continue
                elif seek_rule == DBFindRule.LOWER_OR_EQUAL:
                    if val <= value:
                        continue
                elif seek_rule == DBFindRule.GREATER:
                    if val > value:
                        continue
                elif seek_rule == DBFindRule.GREATER_OR_EQUAL:
                    if val >= value:
                        continue
                all_items_found = False

            if all_items_found:
                answer.append(item)

        return answer



    # region История изменений
    def history_undo(self):
        event_type: EventType
        guid: uuid.UUID
        old_row: DBStorableRow
        new_row: DBStorableRow
        if not self.history_can_undo():
            return
        event_type, guid, new_item, old_item = self._history[self._history_pointer]
        self._disable_notify()
        notify_event_type = None
        notify_event_object = None
        if event_type == EventType.ITEM_ADDED:
            self.delete(new_item, False, True)
            notify_event_type = EventType.ITEM_DELETED
            notify_event_object = EventObject(new_item)

        elif event_type == EventType.ITEM_DELETED:
            self.add(new_item, False, True)
            notify_event_type = EventType.ITEM_ADDED
            notify_event_object = EventObject(new_item)

        elif event_type == EventType.ITEM_CHANGED:
            old_item.save(self._item_states[guid], False, True)
            old_item.save(self._items[guid], False, True)
            notify_event_type = EventType.ITEM_CHANGED
            #notify_event_object = self._items[guid]
            notify_event_object = EventObject(self._items[guid], new_item)
        self._history_pointer-=1
        self._enable_notify()
        self.notify_listeners(notify_event_type, notify_event_object)
        self.notify_listeners(EventType.HISTORY_CHANGED, EventObject(self))



    def history_can_undo(self):
        return self._history_pointer >= 0


    def history_redo(self):
        event_type: EventType
        guid: uuid.UUID
        old_item: DBStorableRow
        new_item: DBStorableRow

        if not self.history_can_redo():
            return
        self._history_pointer += 1
        event_type, guid, new_item, old_item = self._history[self._history_pointer]
        self._disable_notify()
        notify_event_type = None
        notify_event_object = None
        if event_type == EventType.ITEM_ADDED:
            self.add(new_item, False, True)
            notify_event_type = EventType.ITEM_ADDED
            notify_event_object = EventObject(new_item)
        elif event_type == EventType.ITEM_DELETED:
            self.delete(new_item, False, True)
            notify_event_type = EventType.ITEM_DELETED
            notify_event_object = EventObject(new_item)
        elif event_type == EventType.ITEM_CHANGED:
            new_item.save(self._items[guid], False, True)
            new_item.save(self._item_states[guid], False, True)
            notify_event_type = EventType.ITEM_CHANGED
            #notify_event_object = self._items[guid]
            notify_event_object = EventObject(self._items[guid], old_item)
        self._enable_notify()
        self.notify_listeners(notify_event_type, notify_event_object)
        self.notify_listeners(EventType.HISTORY_CHANGED, EventObject(self))

    def history_can_redo(self):
        return self._history_pointer < len(self._history) - 1

    def history_clear(self):
        self._history.clear()
        self._history_pointer = -1
        self.notify_listeners(EventType.HISTORY_CHANGED, EventObject(self))



    def history_commit(self, notifier: Optional[EventPublisher]):
        if notifier:
            notifier.notify_listeners(EventType.OPERATION_BEGIN, EventProgressObject(msg='Сохранение',cur_val=0, max_val=math.inf, level=basic.default_notify_level))
        #items_added: Dict[uuid.UUID, Tuple[EventType, uuid.UUID, DBStorableRow, Optional[DBStorableRow]]] = {}
        #items_changed: Dict[uuid.UUID, Tuple[EventType, uuid.UUID, DBStorableRow, Optional[DBStorableRow]]] = {}
        #items_deleted: Dict[uuid.UUID, Tuple[EventType, uuid.UUID, DBStorableRow, Optional[DBStorableRow]]] = {}
        added_guids: List[uuid.UUID] = []
        changed_guids: List[uuid.UUID] = []
        deleted_guids: List[uuid.UUID] = []

        del self._history[self._history_pointer + 1:]

        event_type: EventType
        item_guid: uuid.UUID
        old_item: DBStorableRow
        new_item: DBStorableRow

        history: List[Tuple[EventType, EventObject]]
        #remove_list = []
        delete_items: Dict[uuid.UUID, DBStorableRow] = {}
        for i, (event_type, item_guid, new_item, old_item) in enumerate(list(self._history)):
            if event_type == EventType.ITEM_ADDED:
                #items_added[item_guid] = event_type, item_guid, new_item, old_item
                added_guids.append(item_guid)
            elif event_type == EventType.ITEM_DELETED:
                #items_deleted[item_guid] = event_type, item_guid, new_item, old_item
                deleted_guids.append(item_guid)
                delete_items[item_guid] = new_item
            elif event_type == EventType.ITEM_CHANGED:
                #items_changed[item_guid] = event_type, item_guid, new_item, old_item
                changed_guids.append(item_guid)

            #remove_list.append(i)
        for guid in list(changed_guids):
            if guid in added_guids:
                if guid in changed_guids:
                    changed_guids.remove(guid)
            if guid in deleted_guids:
                if guid in changed_guids:
                    changed_guids.remove(guid)

        for delete_guid in list(deleted_guids):
            if delete_guid in added_guids:
                deleted_guids.remove(delete_guid)
                added_guids.remove(delete_guid)
                if delete_guid in delete_items.keys():
                    del delete_items[delete_guid]


        number_operations = len(added_guids) + len(changed_guids) + len(deleted_guids)
        current_operation = 1
        if number_operations == 0:
            number_operations = 1

        if notifier:
            notifier.notify_listeners(EventType.OPERATION_BEGIN, EventProgressObject(msg=f'Сохранение {self.name}',cur_val=current_operation, max_val=number_operations, level=basic.default_notify_level))

        self.data_adapter.disable_commit()
        for a_guid in added_guids:
            val = self.get(a_guid)
            if val is not None:
                h_item = EventType.ITEM_ADDED, a_guid, val, None
                self._save_to_db(h_item)
                if notifier:
                    notifier.notify_listeners(EventType.OPERATION_STEP, EventProgressObject(msg=f'Сохранение {self.name}',cur_val=current_operation, max_val=number_operations, level=basic.default_notify_level))
            else:
                self.dataset.logger.error(f'{self} не найден элемент для добавления {self.name} {a_guid}')
            current_operation+=1
        for c_guid in changed_guids:
            val = self.get(c_guid)
            h_item = EventType.ITEM_CHANGED, c_guid, val, None
            if val is not None:
                self._save_to_db(h_item)
                if notifier:
                    notifier.notify_listeners(EventType.OPERATION_STEP, EventProgressObject(msg=f'Сохранение {self.name}',cur_val=current_operation, max_val=number_operations, level=basic.default_notify_level))
            else:
                self.dataset.logger.error(f'{self} не найден элемент для запии {self.name} {c_guid}')
            current_operation+=1
        for d_guid in deleted_guids:
            val = delete_items[d_guid]
            if val is not None:
                h_item = EventType.ITEM_DELETED, d_guid, val, None
                self._save_to_db(h_item)
                if notifier:
                    notifier.notify_listeners(EventType.OPERATION_STEP, EventProgressObject(msg=f'Сохранение {self.name}',cur_val=current_operation, max_val=number_operations, level=basic.default_notify_level))
            else:
                self.dataset.logger.error(f'{self} не найден элемент для запии {self.name} {d_guid}')
            current_operation+=1
        self.history_clear()
        self.data_adapter.enable_commit()
        if notifier:
            notifier.notify_listeners(EventType.OPERATION_END, EventProgressObject(msg=f'Сохранение {self.name} завершено',cur_val=number_operations, max_val=number_operations, level=basic.default_notify_level))
        self.notify_listeners(EventType.HISTORY_CHANGED, EventObject(self))



    def history_length(self):
        return len(self._history)

    @property
    def history_items(self):
        return self._history

    def _save_to_db(self, history_item: Tuple[EventType, uuid.UUID, DBStorableRow, Optional[DBStorableRow]]):
        """непосредственная запись элемента в базу данных"""
        event_type = history_item[0]
        #guid = history_item[1]
        row: DBStorableRow
        row = history_item[2]
        #if history_item[3] is None:
        #    row = history_item[2]
        #else:
        #    row = history_item[3]
        if event_type in [EventType.ITEM_ADDED, EventType.ITEM_DELETED, EventType.ITEM_CHANGED]:
            db_adapter_row: DBAdapterRow = DBAdapterRow()
            db_adapter_row.guid = row.guid
            db_adapter_row.table_name = row.table.name
            for field_name, (prop_type, e_type) in row.get_properties().items():
                if prop_type in [PropertyType.GENERIC, PropertyType.ENUM, PropertyType.CLASS_INSTANCE, PropertyType.LIST_SPLITTED]:
                    db_adapter_row.field_types[field_name] = e_type
                    if prop_type == PropertyType.GENERIC:
                        if hasattr(row, field_name):
                            db_adapter_row.fields[field_name] = getattr(row, field_name)
                        else:
                            db_adapter_row.fields[field_name] = None

                    elif prop_type == PropertyType.LIST_SPLITTED:
                        db_adapter_row.field_types[field_name] = str
                        output_str = None

                        if hasattr(row, field_name):
                            values = getattr(row, field_name)
                            if type(values) == list:
                                if e_type == str:
                                    output_str = '\n'.join([str(item) for item in getattr(row, field_name)])
                                elif e_type == int:
                                    output_str = '\n'.join([str(item) for item in getattr(row, field_name)])
                                elif e_type == float:
                                    output_str = '\n'.join([str(item) for item in getattr(row, field_name)])
                                elif e_type == bool:
                                    output_str = '\n'.join([str(item) for item in getattr(row, field_name)])
                                elif issubclass(e_type, Enum):
                                    output_str = '\n'.join([str(item.value) for item in getattr(row, field_name)])
                                elif issubclass(e_type, DBStorableRow):
                                    output_str = '\n'.join([str(item.guid) for item in getattr(row, field_name)])

                            if not output_str:
                                output_str = None
                        else:
                            output_str = None
                        db_adapter_row.fields[field_name] = output_str
                    elif prop_type == PropertyType.CLASS_INSTANCE:
                        db_adapter_row.field_types[field_name] = uuid.UUID
                        if hasattr(row, field_name):
                            class_item: DBStorableRow = getattr(row, field_name)
                            if class_item is not None:
                                db_adapter_row.fields[field_name] = class_item.guid
                            else:
                                db_adapter_row.fields[field_name] = class_item
                        else:
                            db_adapter_row.fields[field_name] = None
                    elif prop_type == PropertyType.ENUM:
                        db_adapter_row.field_types[field_name] = int
                        if hasattr(row, field_name):
                            enum_item: Enum = getattr(row, field_name)
                            if enum_item is not None:
                                db_adapter_row.fields[field_name] = enum_item.value
                            else:
                                db_adapter_row.fields[field_name] = enum_item
                        else:
                            db_adapter_row.fields[field_name] = None
            if event_type == EventType.ITEM_ADDED:
                self.data_adapter.insert(db_adapter_row)
            elif event_type == EventType.ITEM_DELETED:
                self.data_adapter.delete(db_adapter_row)
            elif event_type == EventType.ITEM_CHANGED:
                self.data_adapter.update(db_adapter_row)
        else:
            self.dataset.logger.error(f'{self} _save_to_db неизвестный тип {event_type}')



    def read_from_db(self, filter_rules: List[Tuple[str, Any, 'DBFindRule']], notifier: Optional[EventPublisher], load_order: Optional[List[Tuple[str, bool]]]=None, level:int=basic.default_notify_level, add_to_table: bool = True):
        """непосредственное чтение элементов из базы данных"""
        #if filter_rules:
        #    for f_name, f_value, f_rule in filter_rules:
        #        if f_name == '_guid':
        #            if self.get(f_value) is not None:
        #                return
        self._table_loading = True
        if notifier:
            notifier.notify_listeners(EventType.OPERATION_BEGIN, EventProgressObject(msg=f'Чтение {self.name}',cur_val=0, max_val=math.inf, level=level))
        table_properties: Dict[str, Tuple[PropertyType, Type]] = self.table_type.get_properties()
        template_row: DBAdapterRow = DBAdapterRow()
        template_row.table_name = self.name
        for field_name, (prop_type, f_type) in table_properties.items():
            if prop_type  == PropertyType.GENERIC:
                template_row.fields[field_name] = None
                template_row.field_types[field_name] = f_type
            elif prop_type == PropertyType.CLASS_INSTANCE:
                template_row.field_types[field_name] = uuid.UUID
                template_row.fields[field_name] = None
            elif prop_type == PropertyType.ENUM:
                template_row.field_types[field_name] = int
                template_row.fields[field_name] = None
            elif prop_type == PropertyType.LIST_SPLITTED:
                template_row.field_types[field_name] = str
                template_row.fields[field_name] = None
            else:
                self.dataset.logger.error(f'({self.name}) Невозможно выполнить чтение таблицы {self.name} поле {field_name} имеет неизвестный тип {prop_type.name}')

        db_items = self.data_adapter.read_multiple(template_row, filter_rules, load_order)
        number_operations = len(db_items)
        if number_operations==0:
            number_operations = 1
        current_number = 1
        if notifier:
            notifier.notify_listeners(EventType.OPERATION_BEGIN, EventProgressObject(msg=f'Чтение {self.name}',cur_val=current_number, max_val=number_operations, level=level)) #EventObject(self, val=len(db_items)))
        self.disable_listen()

        result = []

        for db_item in db_items:
            new_row = self.table_type(self)
            new_row.table = self
            new_row.set_guid(db_item.guid)
            if self.get(db_item.guid) is not None:
                continue
            can_add = True
            for field_name, (prop_type, f_type) in table_properties.items():
                if prop_type == PropertyType.GENERIC:
                    setattr(new_row, field_name, db_item.fields[field_name])
                elif prop_type == PropertyType.ENUM:
                    try:
                        enum_val = db_item.fields[field_name]
                        if enum_val is None:
                            enum_instance = f_type(0)
                        else:
                            enum_instance = f_type(enum_val)
                        setattr(new_row, field_name, enum_instance)
                    except Exception as ex:
                        self.dataset.logger.error(f'({self.name}) Ошибка преобразования значения {db_item.fields[field_name]} в тип {f_type} {ex}')
                        setattr(new_row, field_name, None)
                        can_add = False
                elif prop_type == PropertyType.LIST_SPLITTED:
                    try:
                        list_data = db_item.fields[field_name]
                        if list_data is not None:
                            split_data = list_data.split('\n')
                            if f_type == str:
                                split_data = [item for item in split_data]
                            elif f_type == int:
                                split_data = [int(item) for item in split_data]
                            elif f_type == float:
                                split_data = [float(item) for item in split_data]
                            elif f_type == bool:
                                split_data = [bool(item) for item in split_data]
                            elif issubclass(f_type, Enum):
                                split_data = [f_type(int(item)) for item in split_data]
                            elif issubclass(f_type, DBStorableRow):
                                lookup_table: DBStorableTable = self.dataset.get_table(f_type)
                                if lookup_table is None:
                                    self.dataset.logger.error(f'({self.name}) Ошибка поиска справочной таблицы типа {f_type}')
                                    can_add = False
                                answer = []
                                for guid_str in list(split_data):
                                    guid = uuid.UUID(guid_str)
                                    class_instance = lookup_table.get(guid)
                                    if not class_instance:
                                        self.dataset.logger.error(f'({self.name}) Ошибка поиска справочной таблицы типа {f_type} значения {guid}')
                                        can_add = False
                                    else:
                                        answer.append(class_instance)
                                split_data = answer
                            setattr(new_row, field_name, split_data)
                        else:
                            setattr(new_row, field_name, [])
                    except Exception as ex:
                        self.dataset.logger.error(f'({self.name}) Ошибка преобразования значения {db_item.fields[field_name]} в тип {f_type} {ex}')
                        setattr(new_row, field_name, None)
                        can_add = False

                elif prop_type == PropertyType.CLASS_INSTANCE:
                    # noinspection PyTypeChecker
                    lookup_table: DBStorableTable = self.dataset.get_table(f_type)
                    if lookup_table is not None:
                        lookup_guid = db_item.fields[field_name]
                        if lookup_guid is None:
                            setattr(new_row, field_name, None)
                        else:
                            class_instance = lookup_table.get(lookup_guid)
                            if class_instance is not None:
                                setattr(new_row, field_name, class_instance)
                            else:
                                setattr(new_row, field_name, None)
                                self.dataset.logger.error(f'({self.name}) В таблице {lookup_table.name} не найден объект {lookup_guid}')
                                can_add = False
                    else:
                        self.dataset.logger.error(f'({self.name}) Ошибка поиска справочной таблицы типа {f_type}')
                        can_add = False

                else:
                    self.dataset.logger.error(f'({self.name}) Неизвестный тип в таблице {self.name} поля {field_name} {prop_type.name} {f_type}')
                    can_add = False
            if can_add:
                if add_to_table:
                    self.add(new_row, False, False)
                else:
                    result.append(new_row)
            else:
                self.dataset.logger.error(f'{self} таблица ({self.name}) строка {new_row.guid} не добавлена')
            if notifier:
                notifier.notify_listeners(EventType.OPERATION_STEP,EventProgressObject(msg=f'Чтение {self.name}',cur_val=current_number, max_val=number_operations, level=level)) # EventObject(self, val=current_number))
            current_number +=1
        self.enable_listen()
        if number_operations==0:
            number_operations = 1
        if notifier:
            notifier.notify_listeners(EventType.OPERATION_END, EventProgressObject(msg=f'Чтение {self.name}',cur_val=number_operations, max_val=number_operations, level=level)) #EventObject(self, val=len(db_items)))
        self._table_loading = False
        return result

    # endregion



class DBAdapter:
    type_association: Dict[Type, str] # ключ - внутренний тип данных python, значение - тип данных конкретного типа базы данных
    type_association_sizes: Dict[Type, int]
    connected: bool
    logger: Logger
    name: str
    field_prefix = '['
    field_postfix = ']'
    table_prefix = '['
    table_postfix = ']'
    _should_commit: bool

    def __init__(self, logger: Logger = Logger(), name: str = ''):
        self.connected = False
        self.logger = logger
        self.name = name
        self._should_commit = True

    def connect(self, *args):
        """ Подключение к базе данных """
        if self._connect(*args):
            self.connected = True
            return True
        else:
            self.logger.error(f'({self.name}) Ошибка подключения {self.name} {args}')
        return False

    def _connect(self, *args):
        """ Функция подключения должна быть реализована в наследуемом классе"""
        raise NotImplementedError('Функция _connect должна быть реализована в наследуемом классе')


    def disconnect(self):
        """ Отключение от базы данных """
        if self._disconnect():
            self.connected = False
        else:
            self.logger.error(f'({self.name}) Ошибка отключения {self.name}')

    def _disconnect(self, *args):
        """ Функция отключения должна быть реализована в наследуемом классе"""
        raise NotImplementedError('Функция _disconnect должна быть реализована в наследуемом классе')

    def _execute_write_sql_cmd(self, sql_cmd: str, values: Optional[List[Any]])->bool:
        """ Функция записи команды SQL должна быть реализована в наследуемом классе """
        raise NotImplementedError('Функция _execute_write_sql_cmd должна быть реализована в наследуемом классе')

    def _execute_read_sql_cmd(self, sql_cmd: str, sql_items: Optional[List]) ->List[Any]:
        """ Функция чтения команды SQL должна быть реализована в наследуемом классе """
        raise NotImplementedError('Функция _execute_read_sql_cmd должна быть реализована в наследуемом классе')

    def insert(self, row: DBAdapterRow) -> bool:
        """ Добавить строку в БД """

        insert_sql_cmd = f'INSERT INTO {self.table_prefix}{row.table_name}{self.table_postfix}'
        values_list = []
        field_names = '('
        field_marks = ''

        for field_name in row.fields.keys():
            field_names += f'{self.field_prefix}{field_name}{self.field_postfix}, '
            field_marks += '?, '
            values_list.append(self._conv_to_db_val(row.fields[field_name], row.field_types[field_name]))
        field_names = field_names.rstrip(', ')
        field_names += ')'
        field_marks = field_marks.rstrip(', ')
        insert_sql_cmd +=f'{field_names} VALUES ({field_marks})'
        if __debug__:
            self.logger.debug(f'({self.name}){insert_sql_cmd} {values_list}')
        return self._execute_write_sql_cmd(insert_sql_cmd, values_list)

    def update(self, row: DBAdapterRow) -> bool:
        update_sql_cmd = f'UPDATE {self.table_prefix}{row.table_name}{self.table_postfix} SET '
        values_list = []
        for field_name in row.fields.keys():
            update_sql_cmd += f'{self.field_prefix}{field_name}{self.field_postfix}=?, '
            values_list.append(self._conv_to_db_val(row.fields[field_name], row.field_types[field_name]))
        values_list.append(self._conv_to_db_val(row.guid, uuid.UUID))
        update_sql_cmd = update_sql_cmd.rstrip(', ')
        update_sql_cmd += f' WHERE {self.field_prefix}_guid{self.field_postfix}=?' #{self._conv_to_db_val(item.guid, uuid.UUID, True)}'
        if __debug__:
            self.logger.debug(f'({self.name}) {update_sql_cmd} {values_list}')
        return self._execute_write_sql_cmd(update_sql_cmd, values_list)

    def delete(self, row: DBAdapterRow) -> bool:
        """ Удалить одну строку из БД """
        values_list = [self._conv_to_db_val(row.guid, uuid.UUID)]
        delete_sql_cmd = f'DELETE FROM {self.table_prefix}{row.table_name}{self.table_postfix} WHERE {self.field_prefix}_guid{self.field_postfix}=?'
        if __debug__:
            self.logger.debug(f'({self.name}) {delete_sql_cmd} {values_list}')

        return self._execute_write_sql_cmd(delete_sql_cmd, values_list) # self._conv_to_db_val(item.guid, uuid.UUID, False))

    def is_table_exists(self, table: str):
        if self.connected:
            if table in self._structure_get_dbtable_names():
                return True
        return False

    @staticmethod
    def _conv_to_db_val(val: Any, val_type: Type) -> Any:
        """ Функция преобразования значения из типа python к типу БД """
        raise NotImplementedError('Функция _conv_to_db_val должна быть реализована в наследуемом классе')


    @staticmethod
    def _conv_from_db_val(db_val: Any, output_type: Any) -> Any:
        """ Функция преобразования значения из типа в БД к типу python """
        raise NotImplementedError('Функция _conv_from_db_val должна быть реализована в наследуемом классе')

    def read_multiple(self, template_row: DBAdapterRow, filter_fields: List[Tuple[str, Any, 'DBFindRule']], load_order: Optional[List[Tuple[str, bool]]]=None) -> List[DBAdapterRow]:
        """ Прочесть множество строк из БД """
        fields_list_str = ''
        where_list_str = ''
        for f_name in template_row.fields.keys():
            fields_list_str += f'{self.field_prefix}{f_name}{self.field_postfix}, '
        fields_list_str = fields_list_str.rstrip(', ')
        where_items = []
        if filter_fields:
            for field_name, field_value, field_rule in filter_fields:
                rule_sign = '='
                if field_rule in [DBFindRule.EQUAL, DBFindRule.EQUAL_OR_NULL]:
                    rule_sign = '='
                elif field_rule in [DBFindRule.NOT_EQUAL, DBFindRule.NOT_EQUAL_OR_NULL]:
                    rule_sign = '<>'
                elif field_rule in [DBFindRule.GREATER, DBFindRule.GREATER_OR_NULL]:
                    rule_sign = '>'
                elif field_rule in [DBFindRule.LOWER, DBFindRule.LOWER_OR_NULL]:
                    rule_sign = '<'
                elif field_rule in [DBFindRule.GREATER_OR_EQUAL, DBFindRule.GREATER_OR_EQUAL_OR_NULL]:
                    rule_sign = '>='
                elif field_rule in [DBFindRule.LOWER_OR_EQUAL, DBFindRule.LOWER_OR_EQUAL_OR_NULL]:
                    rule_sign = '<='
                if field_name in template_row.fields.keys():
                    if field_rule == DBFindRule.LIST:
                        where_list_str += f'{self.field_prefix}{field_name}{self.field_postfix} in (SELECT {self.field_prefix}child_guid{self.field_postfix} FROM {self.table_prefix}{field_value[0]}{self.table_postfix} WHERE {self.table_prefix}parent_guid{self.table_postfix}=?) AND '
                        where_items.append(self._conv_to_db_val(field_value[1], template_row.field_types[field_name]))
                    else:
                        if field_value is not None:
                            if field_rule not in [DBFindRule.EQUAL_OR_NULL, DBFindRule.NOT_EQUAL_OR_NULL, DBFindRule.LOWER_OR_NULL, DBFindRule.LOWER_OR_EQUAL_OR_NULL, DBFindRule.GREATER_OR_NULL, DBFindRule.GREATER_OR_EQUAL_OR_NULL]:
                                where_list_str += f'{self.field_prefix}{field_name}{self.field_postfix}{rule_sign}? AND '
                                where_items.append(self._conv_to_db_val(field_value,template_row.field_types[field_name]))
                            else:
                                where_list_str += f'({self.field_prefix}{field_name}{self.field_postfix}{rule_sign}? OR {self.field_prefix}{field_name}{self.field_postfix}{rule_sign} is Null) AND '
                                where_items.append(self._conv_to_db_val(field_value, template_row.field_types[field_name]))
                        else:
                            if field_rule == DBFindRule.EQUAL:
                                where_list_str += f'{self.field_prefix}{field_name}{self.field_postfix} is Null AND '
                            elif field_rule == DBFindRule.NOT_EQUAL:
                                where_list_str += f'{self.field_prefix}{field_name}{self.field_postfix} is not Null AND '
                else:
                    self.logger.error(f'({self.name}) Поле {field_name} не найдено среди полей {template_row.fields.keys()}')
        where_list_str = where_list_str.rstrip(' AND ')
        if not where_list_str:
            select_sql_str = f'SELECT {fields_list_str} FROM {self.table_prefix}{template_row.table_name}{self.table_postfix}'
        else:
            select_sql_str = f'SELECT {fields_list_str} FROM {self.table_prefix}{template_row.table_name}{self.table_postfix} WHERE {where_list_str}'
        order_by_str = ''
        if load_order:
            for fn, asc_order in load_order:
                if asc_order:
                    asc_order_str = 'ASC'
                else:
                    asc_order_str = 'DESC'
                order_by_str += f'{self.field_prefix}{fn}{self.field_postfix} {asc_order_str}, '

        if order_by_str:
            order_by_str = order_by_str.rstrip(', ')
            select_sql_str += f' ORDER BY {order_by_str}'
        if __debug__:
            self.logger.debug(f'({self.name}) {select_sql_str} {where_items}')
        read_items = self._execute_read_sql_cmd(select_sql_str, where_items)
        answer = []
        for item in read_items:
            new_item = DBAdapterRow()
            for i, field_name in enumerate(list(template_row.fields.keys())):
                new_item.fields[field_name] = self._conv_from_db_val(item[i], template_row.field_types[field_name])
                new_item.field_types[field_name] = template_row.field_types[field_name]
            if '_guid' in new_item.fields.keys():
                new_item.guid = new_item.fields['_guid']
            answer.append(new_item)
        return answer


    def disable_commit(self):
        self._should_commit = False
        self._disable_commit()

    def _disable_commit(self):
        raise NotImplementedError('Функция _disable_commit должна быть реализована в наследуемом классе')

    def enable_commit(self):
        self._should_commit = True
        self._enable_commit()

    def _enable_commit(self):
        raise NotImplementedError('Функция _enable_commit должна быть реализована в наследуемом классе')


    # region Создание и удаление таблиц

    def create_table(self, table: DBStorableTable):
        """ Создать таблицу из БД """
        if self.connected:
            fields_str = ''
            for field_name, db_field_type, db_field_size in self._get_table_structure(table):
                if db_field_size is not None:
                    fields_str += f'{self.field_prefix}{field_name}{self.field_postfix} {db_field_type} ({db_field_size}), '
                else:
                    fields_str += f'{self.field_prefix}{field_name}{self.field_postfix} {db_field_type}, '
            fields_str = fields_str.rstrip(', ')
            create_table_sql = f'CREATE TABLE {self.table_prefix}{table.name}{self.table_postfix}({fields_str})'
            if __debug__:
                self.logger.debug(f'({self.name}) {create_table_sql}')
            return self._execute_write_sql_cmd(create_table_sql, None)
        else:
            self.logger.error(f'({self.name}) Соединение с базой данных не установлено')
        return False

    def _get_table_structure(self, table: DBStorableTable)->List[Tuple[str, str, int]]:
        answ: List[Tuple[str, str, int]] = []
        if uuid.UUID not in self.type_association.keys():
            self.logger.error(f'({self.name}) Для поля типа uuid.UUID нет соответствующего типа в конфигурации адаптера данных type_association')
            return answ
        elif int not in self.type_association.keys():
            self.logger.error(f'({self.name}) Для поля типа int нет соответствующего типа в конфигурации адаптера данных type_association')
            return answ

        for field_name, (f_type, f_exact_type) in table.table_type.get_properties().items():
            db_field_type = None
            db_field_size = 0

            if f_type == PropertyType.GENERIC:
                if f_exact_type in self.type_association.keys():
                    db_field_type = self.type_association[f_exact_type]
                    db_field_size = self.type_association_sizes[f_exact_type]
            elif f_type == PropertyType.ENUM:
                db_field_type = self.type_association[int]
                db_field_size = self.type_association_sizes[int]
            elif f_type == PropertyType.CLASS_INSTANCE:
                db_field_type = self.type_association[uuid.UUID]
                db_field_size = self.type_association_sizes[uuid.UUID]
            elif f_type == PropertyType.LIST_SPLITTED:
                db_field_type = self.type_association[str]
                db_field_size = self.type_association_sizes[str]
            else:
                self.logger.error(f'({self.name}) Для таблицы {table.name} поля {field_name} типа {f_exact_type} нет соответствующего типа в конфигурации адаптера type_association')
                return []
            answ.append((field_name, db_field_type, db_field_size))
        return answ


    def check_table_structure(self, table: DBStorableTable)->bool:
        if self.connected:
            structure_fields_info = self._get_table_structure(table)
            db_fields_info = self._structure_get_dbfields_info(table.name)
            structure_ok = True

            for field_name, field_type, field_size in structure_fields_info:
                field_found = False
                db_type = None
                db_size = None
                for db_fn, db_ft, db_sz in db_fields_info:
                    if field_name == db_fn:
                        field_found = True
                        db_type = db_ft
                        db_size = db_sz
                if field_size is None:
                    db_size = None
                if not field_found or db_size != field_size or db_type != field_type:
                    if not field_found:
                        self.logger.error(f'В таблице {table.name} поле {field_name} не найдено в базе данных')
                    else:
                        if db_size != field_size:
                            self.logger.error(f'В таблице {table.name} поле {field_name} типа {field_type} размер {db_size} должно быть {field_size}')
                        if db_type != field_type:
                            self.logger.error(f'В таблице {table.name} поле {field_name} типа {db_type} должно быть {field_type}')
                    structure_ok = False
            return structure_ok
        return False



    def delete_table(self, table: DBStorableTable):
        """ Удалить таблицу из БД """
        if self.connected:
            drop_table_sql = f'DROP TABLE {self.table_prefix}{table.name}{self.table_postfix}'
            return self._execute_write_sql_cmd(drop_table_sql, None)
        else:
            self.logger.error(f'({self.name}) Соединение с базой данных не установлено')
        return False

    # endregion

    # region Служебные функции

    def _structure_get_number_dbrows(self, table_name: str)->int:
        if self.connected:
            select_str = f'SELECT COUNT(*) FROM {self.table_prefix}{table_name}{self.table_postfix}'
            answ = self._execute_read_sql_cmd(select_str,None)
            if len(answ)==1:
                return answ[0][0]
        return 0

    def _stucture_get_dbrows(self, table_name: str)->List:
        if self.connected:
            select_str = f'SELECT * FROM {self.table_prefix}{table_name}{self.table_postfix}'
            answ = self._execute_read_sql_cmd(select_str,None)
            return answ
        return []

    def _structure_clear_dbtable(self, table_name: str)->bool:
        if self.connected:
            clear_str = f'DELETE FROM {self.table_prefix}{table_name}{self.table_postfix}'
            return self._execute_write_sql_cmd(clear_str, None)
        return False

    #endregion

    # служебные наследуемые функции
    def _structure_get_dbtable_names(self)->List[str]:
        raise NotImplementedError('Функция _structure_get_dbtable_names должна быть реализована в наследуемом классе')

    def _structure_get_dbfields_info(self, table_name: str)->List[Tuple[str, str]]:
        raise NotImplementedError('Функция _structure_get_dbfields_info должна быть реализована в наследуемом классе')






class DBStorableDataset(EventPublisher, EventSubscriber):
    _tables: Dict[Type[DBStorableRow], DBStorableTable]
    _db_adapters: List[DBAdapter]
    logger: Logger



    def __init__(self, logger: Logger = Logger()):
        EventPublisher.__init__(self)
        EventSubscriber.__init__(self)
        self._tables = {}
        self._db_adapters = []
        self.logger = logger

    # region Основные таблицы
    def add_table(self, obj: DBStorableTable):
        if obj.table_type not in self._tables.keys():
            self._tables[obj.table_type] = obj
            if obj.data_adapter not in self._db_adapters:
                self._db_adapters.append(obj.data_adapter)
            obj.register_listener(self)
            self.notify_listeners(EventType.ITEM_ADDED, EventObject(obj))
            return True
        return False

    def delete_table(self, obj: DBStorableTable):
        if obj.table_type in self._tables.keys():
            del self._tables[obj.table_type]
            self.notify_listeners(EventType.ITEM_DELETED, EventObject(obj))
            obj.unregister_listener(self)
            if obj.data_adapter in self._db_adapters:
                self._db_adapters.remove(obj.data_adapter)
            return True
        return False

    def get_tables(self, adapter: DBAdapter):
        answer = []
        for table in self._tables.values():
            if table.data_adapter == adapter:
                answer.append(table)
        return answer


    def get_adapters(self):
        return self._db_adapters

    def get_table(self, table_type: Type[DBStorableRow])->Optional[DBStorableTable]:
        if table_type in self._tables.keys():
            return self._tables[table_type]
        return None

    def new_table(self, table_type: Type[DBStorableRow], instant_save: bool, main_adapter: DBAdapter, table_class:type=DBStorableTable):
        if issubclass(table_class, DBStorableTable):
            new_table: DBStorableTable = table_class(self, f'{table_type.__name__}_s', instant_save, main_adapter)
            new_table.table_type = table_type
            return new_table
        else:
            self.logger.error(f'{self} ошибка создания таблицы типа {table_class}')
            return None

    # endregion

    def disable_commit(self):
        for adapter in self._db_adapters:
            adapter.disable_commit()

    def enable_commit(self):
        for adapter in self._db_adapters:
            adapter.enable_commit()

    def on_notify(self, event_type: EventType, event_object: EventObject):
        EventSubscriber.on_notify(self, event_type, event_object)
        self.notify_listeners(event_type, event_object)



    def have_changes(self):
        for table in self._tables.values():
            if table.history_can_undo():
                return True
        return False


    def _show_table_info(self):
        for table in self._tables.values():
            print(f'Таблица: {table.name} записей: {len(table.get_items())}')
            item: DBStorableRow
            for item in table.get_items():
                for key, (_p_type, _e_type) in item.get_properties().items():
                    print(f'    {key} = {getattr(item, key)}')
            print('\n')
        print('\n\n')


    def _show_structure(self):
        for table in self._tables.values():
            print(f'Таблица: {table.name}')
            # noinspection PyProtectedMember
            for f_n, f_t in table.data_adapter._structure_get_dbfields_info(table.name):
                print(f'\t{f_n} ({f_t})')


    def get_load_order(self)->List[DBStorableTable]:
        tables_level: Dict[Type, int] = {}
        list_to_sort: List[Tuple[Type, int]] = [(key, val) for key, val in tables_level.items()]
        list_to_sort.sort(key=lambda x: x[1])
        table_types = [i[0] for i in list_to_sort]
        answ = []
        for t_t in table_types:
            # noinspection PyTypeChecker
            table = self.get_table(t_t)
            if table:
                answ.append(table)
            else:
                self.logger.error(f'Таблица {table} типа {t_t} не найдена в базе данных')
                return []
        return answ





class MSAccessAdapter(DBAdapter):
    type_association: Dict[Any, Any] = {bool:'BIT',
                                        datetime.datetime:'DATETIME',
                                        datetime.date:'DATETIME',
                                        str:'LONGCHAR',
                                        int:'INTEGER',
                                        float:'DOUBLE',
                                        IntEnum:'INTEGER',
                                        uuid.UUID:'GUID'
                                        }# первое значение, внутренний тип данных python, второе значение - тип данных конкретного типа базы данных

    type_association_sizes: Dict[Any, int] = {  bool:None,
                                                datetime.datetime:None,
                                                datetime.date:None,
                                                str:None,
                                                int:None,
                                                float:None,
                                                IntEnum:None,
                                                uuid.UUID:None}

    _ms_conn: Optional[pyodbc.Connection]
    _file_name: Optional[str]
    def __init__(self, logger: Logger = Logger()):
        super().__init__(logger)
        self._ms_conn = None
        self._file_name = None

    @property
    def file_name(self):
        return self._file_name

    def _connect(self, file_name: str, timeout: Optional[int] = None, create_db: bool = False):
        """ Подключение к базе данных """
        if os.path.exists(file_name) or create_db:
            if not os.path.exists(file_name) and os.path.splitext(file_name)[1]=='.accdb':

                acc_app = None
                # noinspection PyBroadException
                try:
                    acc_app = win32com.client.GetActiveObject('Access.Application')
                    app_existing = True

                except Exception as _ex:
                    app_existing = False

                try:
                    if not app_existing:
                        acc_app = win32com.client.Dispatch('Access.Application')
                    acc_app.DBEngine.Workspaces(0).CreateDatabase(file_name, ';LANGID=0x0409;CP=1252;COUNTY=0', 64)
                    #acc_app.DoCmd.CloseDatabase()
                    if not app_existing:
                        acc_app.Quit()
                except Exception as ex:
                    self.logger.error(f'({self.name}) Файл {file_name} не создан {ex}')
                    return False


            if timeout is None:
                pyodbc.connection_timeout = 60
            else:
                pyodbc.connection_timeout = timeout
            try:
                # https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-lcid/a9eac961-e77d-41a6-90a5-ce1a8b0cdb9c
                # 2057 = 0x0809 English United Kingdom
                # 1049 = 0x0419  Russian Russia  ru-RU
                #pyodbc.setDecimalSeparator(',')
                locale_identifier_str = 'Locale Identifier=1049;'
                #locale_identifier_str = ''
                self._ms_conn = pyodbc.connect(f'DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};{locale_identifier_str}DBQ={file_name}')  # если локаль установлена в русскую
                if self._ms_conn:
                    self._file_name = file_name
                    self.name = os.path.split(self._file_name)[1]
                    if __debug__:
                        self.logger.debug(f'({self.name}) Подключение к {file_name} установлено')
                    return True
                else:
                    self.logger.error(f'({self.name}) Подключение к {file_name} не установлено')

            except Exception as ex:
                self.logger.error(f'({self.name}) Ошибка установки подключения: {ex}')
        else:
            self.logger.warning(f'Файл {file_name} не существует')
        return False


    def _disconnect(self):
        """ Отключение от базы данных """
        if not self._ms_conn:
            self.logger.warning(f'Внутренняя ошибка адаптера. Соединение с MSAccess не установлено.')
            self.connected = False
            return False
        try:
            self._ms_conn.close()
            if __debug__:
                self.logger.debug(f'Подключение с {self._file_name} разорвано.')
            self._ms_conn = None
            self._file_name = None
            self.name = ''
            return True
        except Exception as ex:
            self.logger.error(f'({self.name}) Ошибка разрыва подключения: {ex}')
        return False

    def _disable_commit(self):
        pass

    def _enable_commit(self):
        pass

    def _execute_read_sql_cmd(self, sql_cmd: str, sql_items: Optional[List]) ->List[Any]:
        try:
            cur = self._ms_conn.cursor()
            if sql_items:
                result = cur.execute(sql_cmd, sql_items).fetchall()
            else:
                result = cur.execute(sql_cmd).fetchall()
            cur.close()
            return result
        except Exception as ex:
            self.logger.error(f'({self.name}) Ошибка выполнения {sql_cmd} {sql_items} {ex}')
        return []

    def _execute_write_sql_cmd(self, sql_cmd: str, values: Optional[List[Any]])->bool:
        try:
            cur = self._ms_conn.cursor()
            if values:
                cur.execute(sql_cmd, values)
            else:
                cur.execute(sql_cmd)
            cur.commit()
            cur.close()
            return True
        except Exception as ex:
            self.logger.error(f'({self.name}) Ошибка выполнения {sql_cmd} {values} {ex}')

    @staticmethod
    def _conv_to_db_val(val: Any, val_type: Type) -> Any:
        """ Функция преобразования значения из типа python к типу БД """
        if val_type == uuid.UUID:
            #return f"\'{{{val}}}\'"
            if type(val) == uuid.UUID:
                return f"{{{val}}}"
            else:
                return None
        return val

    @staticmethod
    def _conv_from_db_val(db_val: Any, output_type: Any) -> Any:
        """ Функция преобразования значения из типа в БД к типу python """
        if db_val is not None:
            if output_type == uuid.UUID:
                return uuid.UUID(db_val)
            if output_type == datetime.date and type(db_val)==datetime.datetime:
                db_val: datetime.datetime
                return db_val.date()
        return db_val

    def _structure_get_dbtable_names(self) -> List[str]:
        answ = []
        if self.connected:
            cursor = self._ms_conn.cursor()
            for row in cursor.tables():
                answ.append(row[2])

        return answ

    def _structure_get_dbfields_info(self, table_name: str) -> List[Tuple[str, str, int]]:
        answ = []
        if self.connected:
            try:
                cursor = self._ms_conn.cursor()
                col_info = cursor.columns(f'{table_name}')
                for r in col_info:
                    answ.append((r[3], r[5], r[6]))
            except Exception as ex:
                self.logger.error(f'({self.name}) Ошибка выполнения чтения структуры таблицы {table_name} {ex}')

            #select_str = f'PRAGMA table_info({table_name})'
            #rows = self._execute_read_sql_cmd(select_str, None)
            #for row in rows:
            #    answ.append((row[1], row[2]))
        return answ


class SQLiteAdapter(DBAdapter):
    type_association: Dict[Any, Any] = {bool:'BOOL',
                                        datetime.datetime:'TIMESTAMP',
                                        datetime.date:'DATE',
                                        str:'TEXT',
                                        int:'INTEGER',
                                        float:'REAL',
                                        IntEnum:'INTEGER',
                                        uuid.UUID:'GUID'
                                        }# первое значение, внутренний тип данных python, второе значение - тип данных конкретного типа базы данных
    type_association_sizes: Dict[Any, int] = {  bool:None,
                                                datetime.datetime:None,
                                                datetime.date:None,
                                                str:None,
                                                int:None,
                                                float:None,
                                                IntEnum:None,
                                                uuid.UUID:None}
    _sqlite3_conn: Optional[sqlite3.Connection]
    _file_name: Optional[str]

    def __init__(self, logger: Logger = Logger()):
        super().__init__(logger)
        self._sqlite3_conn = None
        self._file_name = None
        self._should_commit = True

    @property
    def file_name(self):
        return self._file_name

    def _connect(self, file_name: str, timeout: Optional[int] = None, create_db: bool=False):
        """ Подключение к базе данных """
        self.name = os.path.split(file_name)[1]
        if os.path.exists(file_name) or create_db:
            try:
                # https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-lcid/a9eac961-e77d-41a6-90a5-ce1a8b0cdb9c
                # 2057 = 0x0809 English United Kingdom
                # 1049 = 0x0419  Russian Russia  ru-RU
                if timeout is None:
                    timeout = 60
                # для преобразования uuid to GUID и обратно, необходимо зарегистрировать типы
                sqlite3.register_adapter(uuid.UUID, lambda u: u.bytes_le)
                sqlite3.register_converter('GUID', lambda b: uuid.UUID(bytes_le=b))

                sqlite3.register_adapter(bool, int)
                sqlite3.register_converter('BOOL', lambda v: bool(int(v)))

                self._sqlite3_conn =  sqlite3.connect(file_name, timeout, detect_types=sqlite3.PARSE_DECLTYPES) # если локаль установлена в русскую
                if self._sqlite3_conn:
                    self._file_name = file_name
                    if __debug__:
                        self.logger.debug(f'({self.name}) Подключение к {file_name} установлено')
                    return True
                else:
                    self.logger.error(f'({self.name}) Подключение к {file_name} не установлено')

            except Exception as ex:
                self.logger.error(f'({self.name}) Ошибка установки подключения: {ex}')
        else:
            self.logger.warning(f'Файл {file_name} не существует')
        return False


    def _disconnect(self):
        """ Отключение от базы данных """
        if not self._sqlite3_conn:
            self.logger.warning(f'Внутренняя ошибка адаптера. Соединение с SQLite не установлено.')
            self.connected = False
            return False
        try:
            self._sqlite3_conn.close()
            if __debug__:
                self.logger.debug(f'Подключение с {self._file_name} разорвано.')
            self._sqlite3_conn = None
            self._file_name = None
            return True
        except Exception as ex:
            self.logger.error(f'({self.name}) Ошибка разрыва подключения: {ex}')
        return False

    def _execute_read_sql_cmd(self, sql_cmd: str, sql_items: Optional[List]) ->List[Any]:
        try:
            cur = self._sqlite3_conn.cursor()
            if sql_items:
                result = cur.execute(sql_cmd, sql_items).fetchall()
            else:
                result = cur.execute(sql_cmd).fetchall()
            cur.close()
            return result
        except Exception as ex:
            self.logger.error(f'({self.name}) Ошибка выполнения {sql_cmd} {sql_items} {ex}')
        return []

    def _execute_write_sql_cmd(self, sql_cmd: str, values: Optional[List[Any]])->bool:
        try:
            cur = self._sqlite3_conn.cursor()
            if values:
                cur.execute(sql_cmd, values)
            else:
                cur.execute(sql_cmd)
            cur.close()
            if self._should_commit:
                self._sqlite3_conn.commit()
            return True
        except Exception as ex:
            self.logger.error(f'({self.name}) Ошибка выполнения {sql_cmd} {values} {ex}')

    @staticmethod
    def _conv_to_db_val(val: Any, val_type: Type) -> Any:
        """ Функция преобразования значения из типа python к типу БД """

        # if not to_str_obj:
        #    return val
        # else:
        #    self.logger.error(f'Нет функции преобразования в строку')
        return val

    @staticmethod
    def _conv_from_db_val(db_val: Any, output_type: Any) -> Any:
        """ Функция преобразования значения из типа в БД к типу python """
        # if not from_str_obj:
        #    return db_val
        # else:
        #    self.logger.error(f'Нет функции для преобразования из строки')
        return db_val



    def _disable_commit(self):
        pass

    def _enable_commit(self):
        try:
            self._sqlite3_conn.commit()
        except Exception as ex:
            self.logger.error(f'({self.name}) Ошибка выполнения {ex}')

    # region Создание и проверка таблиц

    def _structure_get_dbtable_names(self) -> List[str]:
        answ = []
        if self.connected:
            select_str = f'SELECT * FROM sqlite_schema'
            rows = self._execute_read_sql_cmd(select_str, None)
            for row in rows:
                if row[0] == 'table':
                    answ.append(row[1])
        return answ

    def _structure_get_dbfields_info(self, table_name: str) -> List[Tuple[str, str, int]]:
        answ = []
        if self.connected:
            select_str = f'PRAGMA table_info({table_name})'
            rows = self._execute_read_sql_cmd(select_str, None)
            for row in rows:
                answ.append((row[1], row[2], 0))
        return answ




    # endregion


