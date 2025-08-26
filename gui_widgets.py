import base64
import bisect
import calendar
import configparser


import functools
import inspect

import locale
import math

import os
import datetime
import re
import string
import sys

import threading
import time


from enum import Enum, IntEnum, property

from typing import Union, Optional, List, Callable, Any, Dict, Type, Tuple, TypeVar

import win32api
import wx
import wx.lib
import wx.lib.newevent
import wx.lib.scrolledpanel
import wx.adv
import wx.propgrid as wxpg
import wx.grid
import wx.dataview
import wx.lib.agw
import wx.lib.agw.flatmenu
import wx.lib.agw.labelbook


from basic import Logger, LogLevel, EventSubscriber, EventPublisher, EventType, EventObject, EventProgressObject
from db_data_adapter import DBStorableRow, PropertyType








# подсказки!!!
#(f'max {input_box.GetMaxSize()}') # то значение, которое ограничивается setmaxsize
#(f'effective {input_box.GetEffectiveMinSize()}') #самое маленькое похоже на best
#(f'virtual {input_box.GetVirtualSize()}') # виртуальное - подходит для scrolled, почти равно best virtual
#(f'best virtual {input_box.GetBestVirtualSize()}') # самое лучшее значение (подходит для scrolled
#(f'best {input_box.GetBestSize()}') # лучшее значение но не совсем
#(f'min {input_box.GetMinSize()}')  # то значение, которое ограничивается setminsize


mlogger = Logger(LogLevel.ANY, loger_name='GUI_WIDGETS')



class WxEvents(wx.Window):
    #ThreadEvent = None
    #EVT_THREAD_EVENT = None
    #binded_windows: List[wx.Window] = []

    _wxevent_global: Dict[str, Tuple[wx.PyEvent, wx.PyEventBinder]] = {}
    _wxevents_run_time: Dict[Callable, float] = {}
    _wxevents_lock: Dict[Callable, threading.Lock] = {}
    _wxevents_timer: Dict[Callable, Optional[threading.Timer]] = {}
    _wxevents_func_obj: Dict[Callable, Any] = {}
    _wxevent: Dict[Callable, Tuple[wx.PyEvent, wx.PyEventBinder]]

    # noinspection PyMissingConstructor
    def __init__(self):
        self._wxevents_run_time = {}
        self._wxevents_lock = {}
        self._wxevents_timer = {}
        self._wxevent = {}
        self._wxevents_func_obj = {}

        classes = list(self.__class__.mro())
        for cl in list(classes):
            if not issubclass(cl, WxEvents):
                if cl in classes:
                    classes.remove(cl)
            if cl == WxEvents:
                if cl in classes:
                    classes.remove(cl)
        for cl in classes:
            func_names = []
            attr_name: str
            for attr_name in dir(cl):
                if not hasattr(cl, attr_name):
                    continue

                attr = getattr(cl, attr_name)
                if callable(attr):
                    if not (attr_name.startswith('__') and attr_name.endswith('__')):
                        func_names.append(attr_name)

            #func_names = self.get_debounced_names(cl)

            for f_name in func_names:
                func_callable_decorator = getattr(self, f_name)
                if not hasattr(func_callable_decorator,'__wrapped__'):
                    continue
                f_full_name = f'{type(self).__name__}.{f_name}'
                func_callable = func_callable_decorator.__wrapped__
                if f_full_name not in WxEvents._wxevent_global.keys():
                    WxEvents._wxevent_global[f_full_name] = wx.lib.newevent.NewEvent()
                self._wxevent[func_callable] = WxEvents._wxevent_global[f_full_name]
                self._wxevents_lock[func_callable] = threading.Lock()
                self._wxevents_run_time[func_callable] = 0.0
                self._wxevents_timer[func_callable] = None
                self._wxevents_func_obj[func_callable] = self
                self.Bind(self._wxevent[func_callable][1], WxEvents.recv_func)
                self.Bind(wx.EVT_WINDOW_DESTROY, self.destroyed)

    def destroyed(self, evt: wx.WindowDestroyEvent):
        #evt_obj = evt.GetEventObject()
        #if evt_obj == self:
        for func, timer in self._wxevents_timer.items():
            if timer:
                timer.cancel()
        self._wxevent.clear()
        evt.Skip()


    @staticmethod
    def recv_func(evt: wx.PyEventBinder):
        #noinspection PyUnresolvedReferences
        self_obj: WxEvents = evt.self_obj
        #noinspection PyUnresolvedReferences
        func_obj = evt.func
        #noinspection PyUnresolvedReferences
        args = evt.args
        #noinspection PyUnresolvedReferences
        kwargs = evt.kwargs
        func_obj(self_obj, *args, **kwargs)
        self_obj._wxevents_lock[func_obj].release()
        self_obj._wxevents_run_time[func_obj] = time.time()

    T = TypeVar('T', bound=Callable[..., None])
    @staticmethod
    def debounce(wait_time: float, run_immediately: bool)->Callable[['WxEvents.T'], 'WxEvents.T']:
        def debounce_decorator(func: 'WxEvents.T')->'WxEvents.T':
            @functools.wraps(func)
            def debounce_wrapper(self: WxEvents, *args, **kwargs)->None:
                nonlocal func
                if self._wxevents_timer[func]:
                    self._wxevents_timer[func].cancel()
                now = time.time()

                def send_event_thread():
                    nonlocal func
                    if not self._wxevents_lock[func].locked():
                        if func in self._wxevent.keys():
                            self._wxevents_lock[func].acquire(False)
                            # noinspection PyCallingNonCallable
                            new_event = self._wxevent[func][0](self_obj=self, func=func, args=args, kwargs=kwargs)
                            wx.PostEvent(self, new_event)

                self._wxevents_timer[func] = threading.Timer(wait_time, send_event_thread, )
                self._wxevents_timer[func].start()
                if now - self._wxevents_run_time[func]>=wait_time:
                    if run_immediately:
                        self._wxevents_timer[func].cancel()
                        func(self, *args, **kwargs)
                        self._wxevents_run_time[func] = time.time()

                return None

            return debounce_wrapper

        return debounce_decorator


    @classmethod
    def get_debounced_names(cls, source_class: Type):
        source = inspect.getsource(source_class)
        lines = source.split('\n')
        names = []
        for i, line in enumerate(lines):
            if re.match(rf'^\s*def\s', line):
                next_line = lines[i - 1].strip() if i + 1 < len(lines) else None
                next_line = next_line.lstrip(' ')
                search_line = f'{WxEvents.__name__}.debounce'
                if next_line.startswith('@') and search_line in next_line:
                    func_name = re.sub(r'.*def\s+(\w+)\s*\(.*',r'\1', line)
                    if func_name != line:
                        names.append(func_name)
        return names


def pyinstaller_close_splash():
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        if hasattr(sys, '_MEIPASS'):
            if hasattr(os, '_PYIBoot_SPLASH'):
                import pyi_splash # noqa
                pyi_splash.close()
    except Exception as exc:
        mlogger.error(f'Load complete exception {exc}')


def get_app_settings_folder():
    std_pth = wx.StandardPaths.Get()
    return std_pth.GetUserLocalDataDir()

def get_documents_folder():
    std_pth = wx.StandardPaths.Get()
    return std_pth.GetDocumentsDir()



def get_colour(colour_name: str)->wx.Colour:
    found_color = wx.ColourDatabase().FindColour(colour_name)
    if found_color is not None and found_color[0] > -1:
        return found_color

def _wxdate_to_date(wx_date: wx.DateTime) -> Optional[Union[datetime.datetime, datetime.date]]:
    assert isinstance(wx_date, wx.DateTime)
    if wx_date.IsValid():
        try:
            ymd = map(int, wx_date.FormatISODate().split('-'))
            answ = datetime.date(*ymd)
            return answ
        except Exception as ex:
            mlogger.error(f'_wxdate_to_date Ошибка преобразования {wx_date} {ex}')
    else:
        return None

def _date_to_wxdate(date: Union[datetime.datetime, datetime.date]) -> Optional[wx.DateTime]:
    if date is not None:
        assert isinstance(date, (datetime.datetime, datetime.date))
        tt = date.timetuple()
        dmy = (tt[2], tt[1] - 1, tt[0])
        try:
            answ = wx.DateTime.FromDMY(*dmy)
            return answ
        except Exception as ex:
            mlogger.error(f'_date_to_wxdate Ошибка преобразования {date} {ex}')
    else:
        return None

def _image_to_base64_str(image: wx.Image) -> str:
    try:
        t: bytearray
        t = image.GetData()
        base64img = base64.b64encode(t).decode("utf-8")
        w = image.GetWidth()
        h = image.GetHeight()
        base64opacity = ""
        if image.HasAlpha():
            ta: bytearray
            ta = image.GetAlpha()
            base64opacity = base64.b64encode(ta).decode("utf-8")
        return str(w) + ":" + str(h) + ":" + str(base64img) + ":" + base64opacity
    except Exception as ex:
        mlogger.error("_image_to_base64_str Ошибка преобразования изображения в строку:" + str(ex))
        #Logger.MainLogger.Error(None, inspect.stack()[0][3], "Ошибка преобразования изображения в строку:" + str(ex))
    return ""


def b64_img(image_str: str)-> wx.Image:
    return _base64_str_to_image(image_str)

def _base64_str_to_image(image_str: str) -> wx.Image:
    try:
        splitter = image_str.split(":")
        w = splitter[0]
        h = splitter[1]
        img_base64_str = splitter[2]
        img_base64_opacity = splitter[3]

        image = wx.Image()
        image.Create(int(w), int(h), True)
        t: bytes
        t = base64.b64decode(img_base64_str)
        newt: bytearray
        newt = bytearray(t)
        if img_base64_opacity is not None and len(img_base64_opacity) > 0:
            ta = base64.b64decode(img_base64_opacity)
            alphat: bytearray
            alphat = bytearray(ta)
            image.SetData(newt)
            image.SetAlpha(alphat)
        else:
            image.SetData(newt)
        return image
    except Exception as ex:
        mlogger.error("_base64_str_to_image Ошибка преобразования строки в изображение:" + str(ex))
        #Logger.MainLogger.Error(None, inspect.stack()[0][3], "Ошибка преобразования строки в изображение:" + str(ex))
    return wx.EmptyImage()

def _rescale_image(image: wx.Image, new_size: wx.Size) -> wx.Image:
    new_image = image.Scale(new_size.GetWidth(), new_size.GetHeight(), wx.IMAGE_QUALITY_BICUBIC)
    return new_image

def _rescale_image_to_bitmap(image: wx.Image, new_size: wx.Size)->wx.Bitmap:
    new_image: wx.Image = image.Scale(new_size.GetWidth(), new_size.GetHeight(), wx.IMAGE_QUALITY_BICUBIC)
    return new_image.ConvertToBitmap()


def convert_img_file_to_str(file_name: str, img_width: int):
    if os.path.exists(file_name):
        try:
            img: wx.Image = wx.Image(file_name, wx.BITMAP_TYPE_ANY)
            if img.GetWidth() != img_width:
                new_width = img_width
                new_height = int(img_width / img.GetWidth() * img.GetHeight())
                img = _rescale_image(img, wx.Size(new_width, new_height))
            return _image_to_base64_str(img)
        except Exception as ex:
            mlogger.error(f'convert_img_file_to_str Ошибка преобразования картинки в строку {ex}')

    else:
        mlogger.error(f'convert_img_file_to_str Ошибка преобразования картинки в строку файл не найден {file_name}')
    return ''


def get_avaliable_drive_names():
    drives = []
    # noinspection PyReference
    drives_mask = win32api.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if drives_mask & 1:
            drives.append(f'{letter}:')
        drives_mask >>= 1
    return drives

import colorsys
def light_color(color: wx.Colour, factor: float):
    r,g,b = color.GetRed()/255.0, color.GetGreen()/255.0, color.GetBlue()/255.0

    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if factor>1.0:
        s = max(0.0, s/factor)
        v = 1.0
    else:
        v = max(0.0, min(1.0, v* factor))
    #v = v * factor
    r,g,b = colorsys.hsv_to_rgb(h, s, v)
    return wx.Colour(int(r*255), int(g*255), int(b*255))



class BrushStyle(IntEnum):
    EMPTY = 0
    SOLID = wx.BRUSHSTYLE_SOLID
    HORIZONTAL = wx.BRUSHSTYLE_HORIZONTAL_HATCH
    VERTICAL = wx.BRUSHSTYLE_VERTICAL_HATCH
    RIGHT_DIAGONAL = wx.BRUSHSTYLE_BDIAGONAL_HATCH
    LEFT_DIAGONAL = wx.BRUSHSTYLE_FDIAGONAL_HATCH
    SQUARE = wx.BRUSHSTYLE_CROSS_HATCH
    CROSSDIAG = wx.BRUSHSTYLE_CROSSDIAG_HATCH



class TextAlign(IntEnum):
    ALIGN_LEFT = wx.ALIGN_LEFT
    ALIGN_RIGHT = wx.ALIGN_RIGHT
    ALIGN_BOTTOM = wx.ALIGN_BOTTOM
    ALIGN_TOP = wx.ALIGN_TOP
    ALIGN_CENTER =wx.ALIGN_CENTER
    ALIGN_CENTER_VERTICAL = wx.ALIGN_CENTER_VERTICAL
    ALIGN_CENTER_HORIZONTAL = wx.ALIGN_CENTER_HORIZONTAL
    ALIGN_CENTER_LEFT = wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_LEFT
    ALIGN_CENTER_RIGHT = wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT
    ALIGN_CENTER_TOP = wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_TOP
    ALIGN_CENTER_BOTTOM = wx.ALIGN_CENTER_HORIZONTAL | wx.ALIGN_BOTTOM




class WxCommand:
    Image: Optional[wx.Image]
    Bimap: Optional[wx.Bitmap]

    execute: Callable
    can_execute: Callable
    _checked: bool
    enabled: bool
    iid: int
    name: str
    help_string: str

    accel_entry: Optional[wx.AcceleratorEntry]

    def __init__(self, iid: int, name: str, image_name: Optional[Union[str, wx.Image]]=None, acc_control_key: int = wx.ACCEL_NORMAL, acc_main_key: int=wx.WXK_NONE, execute_func: Callable=None, can_execute_func: Callable = None, help_sring: Optional[str]=None):
        self.iid = iid
        self.name = name
        self.help_string = help_sring
        self._checked = False

        self.accel_entry = wx.AcceleratorEntry(acc_control_key, acc_main_key, iid)
        if acc_control_key not in [wx.ACCEL_ALT, wx.ACCEL_CTRL, wx.ACCEL_NORMAL, wx.ACCEL_SHIFT, wx.WXK_NONE, None]:
            mlogger.error(f'{self} неверно задан акселератор для control key {acc_control_key} id {iid}')
            self.accel_entry = None

        if (acc_control_key == wx.WXK_NONE and acc_main_key == wx.WXK_NONE) or (acc_control_key is None and acc_main_key is None) or (acc_control_key == wx.ACCEL_NORMAL and acc_main_key == wx.WXK_NONE):
            self.accel_entry = None

        if image_name is not None:
            if type(image_name) == str:
                if os.path.exists(image_name):
                    self.Image = _rescale_image(wx.Image(image_name, wx.BITMAP_TYPE_ANY), GuiWidgetSettings.menu_bitmap_size)
                    self.Bitmap = _rescale_image_to_bitmap(self.Image, GuiWidgetSettings.menu_bitmap_size)
                else:
                    self.Image = None
                    self.Bitmap = None
                    mlogger.warning(f'{self} init, не найден файл: {image_name}')
            elif type(image_name) == wx.Image:
                self.Image = _rescale_image(image_name, GuiWidgetSettings.menu_bitmap_size)
                self.Bitmap = _rescale_image_to_bitmap(self.Image, GuiWidgetSettings.menu_bitmap_size)
        else:
            self.Image = None
            self.Bitmap = None

        if can_execute_func is None:
            self.execute = self.always_run_decorator(execute_func)
        else:
            self.execute = self.check_can_execute_decorator(execute_func)
        if can_execute_func is not None:
            self.can_execute = can_execute_func
        else:
            self.can_execute = self.always_run
        #self.update_state()
            # self.Enabled = self.CanExecute()

    @staticmethod
    def always_run():
        return True

    def update_state(self):
        if self.can_execute is None:
            self.enabled = True
        else:
            self.enabled = self.can_execute()

    def check_can_execute_decorator(self, func: Callable):
        def wrapper(*args, **kwargs):
            """A wrapper function"""
            # Extend some capabilities of func
            if self.can_execute:
                if self.can_execute():
                    self.enabled = False
                    func(*args, **kwargs)
                else:
                    self.enabled = False
            else:
                self.enabled = True
                func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    @staticmethod
    def always_run_decorator(func):
        def wrapper(*args, **kwargs):
            """A wrapper function"""
            # Extend some capabilities of func
            if func is not None:
                func(*args, **kwargs)
            else:
                return True

        if func is not None:
            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper
        else:
            return None

    @property
    def checked(self):
        return self._checked

    @checked.setter
    def checked(self, checked: bool):
        self._checked = checked

class BasicWxCommandListener:
    _parent_wnd: wx.Window
    commands_list: List[WxCommand]
    _control_c_command: Optional[WxCommand]

    def __init__(self, parent: wx.Window):
        self._parent_wnd = parent
        # грязный трюк, из-за еще одной ошибки в реализации wxWidgets Control+C не передается в AcceleratorTable корректно
        # придется отлавливать вручную
        _control_c_command = None
        self.commands_list = []

    def bind_wxcommands(self):
        # should be called after commands added
        accel_entries = []
        for i in self.commands_list:
            if i.accel_entry is not None:
                flag = i.accel_entry.GetFlags()
                key_code = i.accel_entry.GetKeyCode()
                # грязный трюк! но по другому никак
                if flag == wx.ACCEL_CTRL and key_code == wx.WXK_CONTROL_C:
                    self._control_c_command = i
                    self._parent_wnd.Bind(wx.EVT_CHAR_HOOK, self._key_hook)
                self._parent_wnd.Bind(wx.EVT_MENU, i.execute, id=i.iid)
                accel_entries.append(i.accel_entry)
        if len(accel_entries) >= 0:
            accel_table = wx.AcceleratorTable(accel_entries)
            self._parent_wnd.SetAcceleratorTable(accel_table)
            # self.SetAcceleratorTable(accel_table)

    def _key_hook(self, evt: wx.KeyEvent):
        evt.Skip()
        if evt.ControlDown() and evt.GetRawKeyCode() == 67:
            self._control_c_command.execute(evt)


    def add_wxcommand(self, cmd_item: WxCommand):
        for cmd in self.commands_list:
            if cmd.iid == cmd_item.iid:
                mlogger.error(f'{self} добавление команды {cmd_item.name} невозможно, такой id {cmd_item.iid} существует')
                return
        self.commands_list.append(cmd_item)
        if __debug__:
            mlogger.debug(f'{self} добавление команды {cmd_item.name}')

    def delete_wxcommand(self, cmd_item: WxCommand):
        deleted = False
        for cmd in list(self.commands_list):
            if cmd.iid == cmd_item.iid:
                self.commands_list.remove(cmd)
                deleted = True
                if __debug__:
                    mlogger.debug(f'{self} удаление команды {cmd_item.name}')
        if not deleted:
            mlogger.error(f'{self} ошибка удаления команды {cmd_item.name} {cmd_item.iid}')

    def update_wxcommands(self):
        for i in self.commands_list:
            i.update_state()

    def clear_wxcommands(self):
        self.commands_list.clear()
        self._control_c_command = None
        self._parent_wnd.SetAcceleratorTable(wx.NullAcceleratorTable)

class ImageList:
    class BuiltInImage(Enum):
        UNKNOWN = 0
        CRITICAL = 1
        ERROR = 2
        WARNING = 3
        INFO = 4
        OK_CHECK = 5
        EMPTY = 6
        STOP = 7

        CHECK_SYMBOL = 100
        UNCHECK_SYMBOL = 101

    image_list: wx.ImageList
    size: wx.Size
    _names: Dict[Union[str, Enum], int]

    # noinspection SpellCheckingInspection
    criticalImgStr = '32:32:AQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAwTkowTcnwDcnwTgowTgowTkpwTkpwTopwToqwToqwToqwTsrwjsrwTwsAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjQl4J2U7sO966yi6qif6KWa56CV5puR5ZiN4pOI446D4Yt+34V53YuA0XBkwDkqAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjQk4KCZ77645EIm5D0f5D4h5D8h5D8i5EAi5UAi5UAj5UEj5UEk5UEj5UQn3IB00GxgwDoqAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjQk4KCZ8MO95UUr5UMm5UYq5UYq5Ucq5Ucq5Ucq5Ucq5Ucq5Ucq5Ucr5Ucq5kUp5kYr2nxvz2ldwDoqAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjQl35qT7r+55kgt5kUp5kkt5kov5kov5kov5kov5kov5kov5kov5kov5kov5kov5kku50gs50ku2XhqzWVYwDoqAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvzUl3JWM7bmx50ov50cr50ov50ou50ou50sw50wx50wx50wx50wx50wx50wx50sw50ou50ou50ov6Eou50sx13NlzGBVwDsrAAAAAQAAAQAAAQAAAQAAAQAAAAAAvzYm25CI67Gq6Uwx6Ekt6Esw50gr6FE26FE250gr6Ewx6E4z6E4z6E4z6E4z6Ewx50gr6FE26FE250gr6Eww6Uwx6U4y1W1fy11QwDwsAAAAAQAAAQAAAQAAAAAAvzYn2YqC6ayj6k806Uwx6U4z6Eku6Eov/vLw/vLw6Ekv6Eku6U406VA26VA26U406Eku6Ekv/vLw/vLw6Eov6Eku6U406k806U811GhaylhLwTwsAAAAAQAAAAAAwDoq2IZ856Wc6lA36k8z6lA26Uwy6Uwy/ezq/////////evq6Usx6Usw6lA26lA26Usw6Usx/evq/////////ezq6Uwy6U0y6lE361E261I40mFUyVRGwT4uAAAAAAAAwTgn5bOs7FI361E161M561I46kou/fTy/////////////////ezp6k006kww6kww6k00/ezp/////////////////fTy6kou61I461Q67VQ57VM6zF9Twz0tAAAAAAAAwTcn4q2m7lA17FQ77FY97FQ7600y+cvD/////////////////////ezo60ox60ox/ezo////////////////////+cvD600y7FQ77FY97VY98FY8yl1Rwj0tAAAAAAAAwTgn4aii71M47Vc+7Vg/7Vg/7VQ660gt+MW9/////////////////////eXg/eXg////////////////////+MW960gt7VQ67Vg/7Vg/7Vg/8Vg+yFtOwz0tAAAAAAAAwTgo36Ob8FU77llA7lpB7lpB7llA7lU77Eou+ca+////////////////////////////////////////+ca+7Eou7lU77llA7lpB7lpB71pB8ltBx1hLwz4uAAAAAAAAwTgo3p2W8Vg/71tD71xE71xE71xE71tD71c+7Uwx+ce+////////////////////////////////+ce+7Uwx71c+71tD71xE71xE71xE8FxE811Ex1VHwz4uAAAAAAAAwTko25eQ81tB8F1F8F5G8F5G8F5G8F5G8F1F71g/7kku+r+2////////////////////////+r+27kku71g/8F1F8F5G8F5G8F5G8F5G8V5G9GBHxVNFwz4uAAAAAAAAwTkp2pGJ9FxE8V5H8V9I8V9I8V9I8V9I8V1G8Fc/8FY9/Ofk/////////////////////////Ofk8FY98Fc/8V1G8V9I8V9I8V9I8V9I8l9I9WFJxU9Cwz4uAAAAAAAAwTop14yE9l9I82FK82FL82FL82FL819J81pD8lxF/u3q/////////////////////////////////u3q8lxF81pD819J82FL82FL82FL9GFL+GNNxEw+wz4uAAAAAAAAwToq1oZ+92FK9GNM9GNN9GNN9GJL9F1G815H/u7s/////////////////////////////////////////u7s815H9F1G9GJL9GNN9GNN9WNN+WZPwkg6wz4uAAAAAAAAwjoq04F4+WRN9WVO9WVP9WVO9WBJ9GJK/u7s////////////////////+8O6+8O6/////////////////////u/s9GJL9WBK9WVO9WVP9mVP+mhRwUU2wz8vAAAAAAAAwjsq0ntw+mdQ92dS9mdS9mZQ9l5I/unm/////////////////////MvD9VQ99VQ9/MvD/////////////////////dzY9l9J9mZR9mdS92hT/GtVwEExwz8vAAAAAAAAwjsr0XVr+WpV+WlU92lU92hS92FL/NHK/////////////////MvE9lpD92RO92RO9lpD/MvD/////////////////dLL92FL92hT92lU+WtW+2xXwD8vxD8vAAAAAAAAvjwszF1Q2G9i+WxX+mtW+GtV+GdR911G/M3G//////////Du91tD+GZQ+GpV+GpV+GZQ92dS/+/u/////////M3G911G+GdS+GtW+m1Y+mxYy0Y2wj8vvz4vAAAAAAAAAAAAujoqylpN1mxf+m9a+21Z+WxY+WhU+F9J/dHM//b1+GlU+WdT+WxY+W1Z+W1Z+WxY+WdS+GlU//b1/dHM+F9J+WhU+W1Z+29b+25aykc2wT8vvD0tAAAAAAAAAAAAAAAAAAAAujoqyVhJ1Wha/HBd/HBb+m5a+mtX+mdS+mZR+mpW+m5Z+m9b+m9b+m9b+m9b+m5Z+mpW+mZR+mdS+mxX+m9b/HFd/XFcy0c2wT4vuz0tAAAAAAAAAAAAAQAAAAAAAAAAAAAAujsqyFRH02NW/XJe/XJe+3Fd+3Bb+3Bb+3Bc+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Bc+3Bb+3Bb+3Fd/XNf/nNfy0c2wT4vuz0tAAAAAAAAAAAAAQAAAQAAAQAAAAAAAAAAAAAAujsrx1FD0l9R/nRh/nVi/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/nVi/3Riy0Y3wT4uuz0tAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAujsrxU0+0VtM/3Zk/3dk/nZj/nZj/nZj/nZj/nZj/nZj/nZj/nZj/nZj/nZj/3hk/3Zky0g3wT4uuz0tAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAuzsrxEk70FZH/3po/3xp/3xp/3xp/3xp/3xp/31p/31p/31q/31q/31q/3poy0g3wT4uuz0tAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAuzwsxEc3xEk6w0g5wkY4wkU3wEQ2wEEzv0Ayvz8vvz0tvjssvjwsvz0twj8vuz0tAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAvz0uwz4uwz4uwz4uwz4uwz4uwz4uwz4uwz8vwz8vwz8vwz8vwz8vvz4vAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAA:AAAAAAAAAAAF6f///////////////+kFAAAAAAAAAAAAAAAAAAAABeX//////////////////+UFAAAAAAAAAAAAAAAAAAXl/////////////////////+UFAAAAAAAAAAAAAAAF5f///////////////////////+UFAAAAAAAAAAAABeX//////////////////////////+UFAAAAAAAAAAXl/////////////////////////////+UFAAAAAAAF5f///////////////////////////////+UFAAAABeX//////////////////////////////////+UFAAXq/////////////////////////////////////+oFEP///////////////////////////////////////xAW////////////////////////////////////////Fhb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFu7/////////////////////////////////////7hYQNev//////////////////////////////////+s1EAUZOuv////////////////////////////////rOhkFAAUZOev/////////////////////////////6zkZBQAAAAUZOev//////////////////////////+s5GQUAAAAAAAUZOev////////////////////////rORkFAAAAAAAAAAUZOev/////////////////////6zkZBQAAAAAAAAAAAAUZOev//////////////////+s5GQUAAAAAAAAAAAAAAAUZOu/////////////////vOhkFAAAAAAAAAAAAAAAAAAUZNUJDQ0NDQ0NDQ0NDQjUZBQAAAAAAAAAAAAAAAAAAAAUQFhYWFhYWFhYWFhYWEAUAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    errorImgStr = '32:32:AQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAmDAjuTgpvTcovzcnvzYnvzYnvzcnvzcovzgpvTkqujkrmTEkAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAApzQnvTcowz0t3G5a64t1+6eN/amR/KOM+p+H+ZuD9JJ55HVg1l5Lwj0uvjorpzUoAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAuzgpwzws6Yl0/7ig/7Wd/7Wf/7Wi/7aj/7Wi/7Oh/7Kg/7Cd/6WR+ZeC84dw3WZRwz0tvDssAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjco1F9M/7Sb/7eh/7mm+ZF67mlQ5Usv4Tse4Tsf4Twf4Tse5Uov7mdO+ot2/6uY+JN/6nNdzkw6vzwtAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvTUn5oNt/7ui/7mk+5qG5Uww4z8k40Mn5EUq5UYr5UYr5UYr5UYr5EUq40Mo40El5kwx/JB8/6CM7XNe11RBvzssAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvTYo5oNt/7qh/7mm8XNb40Ak5UYq5kgt5kku5kku5kgt5kgs5kgs5kgt5kku5kku5kgt5Ucr5EIn8m9W/6WS7G5a1lA9vzwsAAAAAQAAAQAAAQAAAQAAAQAAAAAAtjco015M/7ui/7im721W5UQq5kkv50sy50wy50wy50ku5UIn5Twg5Twg5UIn50ku50wy50wy50sy5kow5UYs8GlS/6KP6WFOykQztzorAAAAAQAAAQAAAQAAAAAAiSsgwj0s/7Sb/7ik8nZe5kYs6Ewx6E406E406E406Ewy50Qp9auf////////9auf50Qp6Ewy6E406E406E406Ewy5kgu83BY/5WD3047wz4uiiwiAAAAAQAAAQAAAAAAuzYo6Ylz/7eh/JuH50gu6E806VE36VE36VE36VE36U8050El////////////////50El6U806VE36VE36VE36VE36E8150sx/ox48nZj00UzvTwuAAAAAQAAAQAAUhoTwz0t/7ig/7ek61Y86k8161M461M561M561M561M561A26UEk////////////////6UEk61A261M561M561M561M561M56lA27Fc9/5yJ30k1wz0uUxsUAQAAAAAAqjQm3G5a/7Sc+5SA6k007FM67FU87FU87FU87FU87FU87FI56kQo////////////////6kQo7FI57FU87FU87FU87FU87FU87FQ761E3/IZy62FOzDwrqjgqAAAAAAAAuDYn64t0/7Se9HRd7FI57Vc97Vc+7Vc+7Vc+7Vc+7Vc+7VU760cs//f2//////////f260cs7VU77Vc+7Vc+7Vc+7Vc+7Vc+7Vc+7FQ79W5Y+H1s0Tgmuj0uAAAAAAAAvzcn+6eN/7Sg71xE7lY+7llB7llB7llB7llB7llB7llB7lc/7Esx/N7Y/////////N7Y7Esx7lc/7llB7llB7llB7llB7llB7llB7lc/8F5F/5WE1TEfwUAwAAAAAAAAvzYn/aiQ/7Sg7VM671lB71tD71tD71tD71tD71tD71tD71lB7k41+9PM////////+9PM7k4171lB71tD71tD71tD71tD71tD71tD71pC7lc+/5qJ1SoYwUAwAAAAAAAAvzYn/KOL/7Of7lU+8FxF8F1G8F1G8F1G8F1G8F1G8F1G8FtE71I6+K2h////////+K2h71I68FtE8F1G8F1G8F1G8F1G8F1G8F1G8FxF71pC/5mH1CUVwUAwAAAAAAAAvzcn+Z6H/7Ge8VhA8l5H8l9I8l9I8l9I8l9I8l9I8l9I8l5G8VY++LGm////////+LGm8VY+8l5G8l9I8l9I8l9I8l9I8l9I8l9I8l5H8lxF/5iG0SEQwkExAAAAAAAAvzco+ZqC/7Cd8lpD819J82FL82FL82FL82FL82FL82FL82BK81pD9YBt////////9YBt81pD82BK82FL82FL82FL82FL82FL82FL82BK815I/5iG0SAPwkExAAAAAAAAvzgp9JF5/66a9GZR9GJM9GRO9GRO9GRO9GRO9GRO9GRO9GRO9F9J94h3////////94h39F9J9GRO9GRO9GRO9GRO9GRO9GRO9GRO9GNN9WdS/5F/0SEQwkExAAAAAAAAtTcp5HVf/qKP+nxo9WNN9WZQ9WZQ9WZQ9WZQ9WZQ9WZQ9WZQ9WRO9V5H9FhA9FhA9V5H9WRO9WZQ9WZQ9WZQ9WZQ9WZQ9WZQ9WZQ9WVO+3Zi9XJhzCoZtzwuAAAAAAAAlS4j1l1K+JaA/pSA9mRO9mdS9mhT9mhT9mhT9mhT9mhT9mhT9mVQ9l9I9VlC9VlC9l9I9mVQ9mhT9mhT9mhT9mhT9mhT9mhT9mhT9mZR/4d05E07yTMhlzEmAAAAAAAAKw4Kwj0u8oZv/6eV+GxY92hT92pV92pV92pV92pV92pV92lT92JM+7mv////////+7mv92JM92lT92pV92pV92pV92pV92pV92lU+W5Z/5F/1ScWwj8vKw4LAAAAAAAAAAAAtjgo3WVR+JF9/5iF+WhU+WtX+WxY+WxY+WxY+WxY+WpW+V9K////////////////+V9K+WpW+WxY+WxY+WxY+WxY+WxY+WtW/4t57FxKzC0ctzwtAAAAAAAAAQAAAAAAShgRwz0t6nJc/p2J/oRw+mtX+m1Z+m5a+m5a+m5a+mxY+mFL////////////////+mFL+mxY+m5a+m5a+m5a+m5Z+m1Y/n5r/IFv0CEQwj8vShgSAAAAAQAAAQAAAAAAAAAAojMmzks57XJc/6GP/YBt+25b+29c+3Bd+3Bd+29c+2hU/byz/////////byz+2hU+29c+3Bd+3Bd+3Bd+29c/n1q/5B+1y4dxjYmozYpAAAAAAAAAQAAAQAAAAAAAAAAAAAAujor1lRB621Z/56M/4Vy/HBd/HFe/HJf/HFe/G9c/GpW/GVR/GVR/GpW/G9c/HFe/HJf/HJf/HFe/4Fv/5B+2jUkyy4fuz8vAAAAAAAAAAAAAQAAAQAAAQAAAAAAAAAAAAAAuTor1VA96GBN/pOA/5OA/ndk/XRh/XRh/XRh/XNg/XNg/XNg/XNg/XRh/XVi/XVi/nhl/456/IFv1y4dyy8fuj0vAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAuTsrykQz30468XRh/5iF/499/4Nw/3ln/3dj/3dk/3dk/3dk/3po/4Jv/4x6/4997FtJ0CAPxzYmuj0vAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAoDMnwz4u0kQy30g16mBM93tp/5OB/5eF/5aE/5WD/5aE/4999XFg5Ew61SYWzC0cwj8voTYoAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAQRUQtToswz0uzDwr0Tgm1TEe1SoY1CUU0SAP0R8O0SEQzCoZyTIhwj8vtTwuQRUQAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAHAkHii4itDstwUAwwUAwwUAwwUAxwkExwkExtDsuiy4jHAkHAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAA:AAAAAAAAAAAAAA5y0f///////9FyDgAAAAAAAAAAAAAAAAAAAAAAASPT////////////////0yMBAAAAAAAAAAAAAAAAAAOZ/////////////////////5kDAAAAAAAAAAAAAAAF5v///////////////////////+YFAAAAAAAAAAAABeX//////////////////////////+UFAAAAAAAAAAXn/////////////////////////////+cFAAAAAAADnP///////////////////////////////5wDAAAAASn//////////////////////////////////ykBAAAG1v//////////////////////////////////1gYAABr/////////////////////////////////////GgADfP////////////////////////////////////98AwnW/////////////////////////////////////9YJEf///////////////////////////////////////xEV////////////////////////////////////////FRb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFdr/////////////////////////////////////2hURjf////////////////////////////////////+NEQky/////////////////////////////////////zIJAxvd///////////////////////////////////dGwMAEEz//////////////////////////////////0wQAAAGH7D///////////////////////////////+wHwYAAAENLuz/////////////////////////////7C4NAQAAAAMWOOv//////////////////////////+s4FgMAAAAAAAUZOu3////////////////////////tOhkFAAAAAAAAAAUZOLT/////////////////////tDgZBQAAAAAAAAAAAAUWLlrf////////////////31ouFgUAAAAAAAAAAAAAAAMNIDVMmd7////////emUw1IA0DAAAAAAAAAAAAAAAAAAEGEBspOEFDQ0NDQTgpGxAGAQAAAAAAAAAAAAAAAAAAAAAAAwkRFRYWFhYVEQkDAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    warningImgStr = '32:32:////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAvno1yX81yX81vno1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAakQey4U8/+ee/+eey4U8akQeAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAwns05rdv/81b/81b5rdvwns0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAn2YszYtD/+eY/6wb/60b/+OPzYtDn2YsAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAx3428c6B/8RK/6oY/6oY/8RK8c6Bx342AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAtHMy1phP/+CA/6wZ/64f/64f/6wZ/+CA1phPtHMyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAxnw1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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJj//9jAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFf////8VAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAXC/////8IFAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABPf///////z0BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAf4////////+AcAAAAAAAAAAAAAAAAAAAAAAAAAAAACef//////////eQIAAAAAAAAAAAAAAAAAAAAAAAAAAAr/////////////CgAAAAAAAAAAAAAAAAAAAAAAAAADsP////////////+wAwAAAAAAAAAAAAAAAAAAAAAAAT3///////////////89AQAAAAAAAAAAAAAAAAAAAAAH5v///////////////+YHAAAAAAAAAAAAAAAAAAAAAnn//////////////////3kCAAAAAAAAAAAAAAAAAAAK/////////////////////woAAAAAAAAAAAAAAAAAA53/////////////////////nQMAAAAAAAAAAAAAAAEp////////////////////////KQEAAAAAAAAAAAAABtT////////////////////////UBgAAAAAAAAAAAAJk//////////////////////////9kAgAAAAAAAAAACf////////////////////////////8JAAAAAAAAAAOd/////////////////////////////50DAAAAAAABKf///////////////////////////////ykBAAAAAAbU////////////////////////////////1AYAAAABUv//////////////////////////////////UgEAAAj7///////////////////////////////////7CAAAEv////////////////////////////////////8SAAAV1P//////////////////////////////////4xUAAA4tQENDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0EvDwAABA4VFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFQ8FAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    infoImgStr = '32:32:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEkqKE1emEViqD1esDlarDlarDlarD1esEFisElmqFFinE0qKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFFGXEliqFl2vUI/QdK3kmMz4ntH7m876mcz3lsr2i8HxaKLdR4bKFl6wFFqrFVGXAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE1ipFl2vbqfgqNn/sd//vej/xvD/yPD/x+//xu7/xO3/wOr/sd/9ndD3i8HxWZfWF12vFVmqAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEVerPHzFnc/7uOT/yvP/k8rvXJ/YMX3FHG29HW69HW69HG69MH7FWpzXjcPtuub/ndD2drHmMHS/FFqtAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD1aqZJ/bqtr/xe7/otT1MoDFInO/J3bBKXnCK3rDLHrDLHrDK3rDKnnCJ3fBI3S/Mn/GlMrwrdz7frfpSYrNE1mrAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEVeqZJ/bqtr/yvP/a6vdJHS/K3nCL3zEMH3FMH3FL33ELnzELnzEL33EMH3FMH3FL3zELHrDJnbAZKXbsuD+e7TnRYjLFVqsAAAAAAAAAAAAAAAAAAAAAAAAAAAAE1akPH3Ep9n+yvP/Y6TaKnjCMX3FM3/HNIDHNIDHMH7GKXnEInXCInXCKXnEMH7GNIDHNIDHM3/HMX7GK3rDXZ/YsN79cazjLHC8FVimAAAAAAAAAAAAAAAAAAAAEEJ8Fl2vmc34w+7/b67gLXvDNIHHN4PIN4PIN4PINYLILHzFocXl////////ocXlLHzFNYLIN4PIN4PIN4PINYHHL33FZqbcotP3XJ3aF16vEkN8AAAAAAAAAAAAAAAAEleoaqPetOH/pNb2LnzEN4LHOoXJOoXJOoXJOoXJN4PIKXrE////////////////KXrEN4PIOoXJOoXJOoXJOoXJN4PIMX7FkMbvhb3rQYPJFVmqAAAAAAAAAAAACihLFVywodP8yfD/QovMOYTJPYjLPojLPojLPojLPojLPIbLLX3G////////////////LX3GPIbLPojLPojLPojLPojLPojLOoXJQozNqNf6XJ3ZF16wCyhLAAAAAAAAElGaTIrNq9r8ms/xN4LIP4jLQYrMQYrMQYrMQYrMQYrMP4nMNoPJpcjm////////pcjmNoPJP4nMQYrMQYrMQYrMQYrMQYrMP4nLOoXJh7/rcq7iL3S+FVObAAAAAAAAEVambKffuOX/bqzgPofKQ4vNRIzNRIzNRIzNRIzNRIzNQ4vNPojLNoTJMIDIMIDIN4TKP4nMQ4zNRIzNRIzNRIzNRIzNRIzNRIzNQInLZKXbi8LvOn/GFVmoAAAAAAAAEFisisLwxe7/TZPQRIzOR4/PR4/PR4/PR4/PR4/PRo/PQozOOofMNITKMoLKMoLKOIbLQYzNRo/PR4/PR4/PR4/PR4/PR4/PR4/PRI3OTJPRodP4RIrNFlyvAAAAAAAAD1esj8X0xu//P4nLSI/PSpHQSpHQSpHQSpHQSpHQSJDQQYvO////////////////////PInNSI/QSpHQSpHQSpHQSpHQSpHQSpHQSJDQQ4zNpdX6Q4nNFVyvAAAAAAAAD1esicDxxO3/Q43MS5PQTZTRTZTRTZTRTZTRTZTRTJTRRpDPNIXL////////////////O4nMSpLQTZTRTZTRTZTRTZTRTZTRTZTRTJPRR5DOpNT5P4XLFlyvAAAAAAAAEFeshr3vw+z/R4/PTpXSUJbTUJbTUJbTUJbTUJbTUJbTTJTSPIrO////////////////PYvOTZTSUJbTUJbTUJbTUJbTUJbTUJbTT5XTSpLQotP5OoPJFlyvAAAAAAAAEFisgbvtwev/S5HQUpbTVJjUVJjUVJjUVJjUVJjUVJjUUZbTQo3P////////////////Qo3PUZbTVJjUVJjUVJjUVJjUVJjUVJjUU5fUT5TRodL4N4DGFlyvAAAAAAAAElmteLLnvOj/XJ/XVJnUV5vVV5vVV5vVV5vVV5vVV5vVVJnURZDQ////////////////RZDQVJnUV5vVV5vVV5vVV5vVV5vVV5vVVZrUXJ7Ymcz0MXrDF12vAAAAAAAAElakWJjWqNj6erbkVprVWp3XWp3XWp3XWp3XWp3XWp3XV5vWSZPT////////////////SZPTV5vWWp3XWp3XWp3XWp3XWp3XWp3XWJvWca7hfLXnJ3C9F1mmAAAAAAAAEUiHPX/FjsTwnM/yV5zWXJ/YXaDYXaDYXaDYXaDYXaDYWp7XTJbU////////////////TJbUWp7XXaDYXaDYXaDYXaDYXaDYXKDYWp7WiL/tVpjVIGi4E0mJAAAAAAAABRUnF16wdLDmtuP/ZKbbXaDYYKLZYKLZYKLZYKLZYKLZXaDYTpjU////////////////TpjUXaDYYKLZYKLZYKLZYKLZYKLZXqHYZaXblcnzMHrDF1+wBhUnAAAAAAAAAAAAFFalSozOkMXwoNP2XqDZYaPaY6TbY6TbY6TbYqTbXaHZTZfW////////////////TZfWXaHZYqTbY6TbY6TbY6TbYqPbYaLajMPvYaDaIWu6GFmmAAAAAAAAAAAAAAAACSRDF12wYJ/bptf4hb3pY6TaZqbbZ6fcZ6fcZqbcX6La////////////////////////X6LaZqbcZ6fcZ6fcZqfcZabbfLfmhbzsIm+9GF6wCiVDAAAAAAAAAAAAAAAAAAAAEk6SKm+7Z6Xfrt38gbvoZ6bbaajdaqndaandZqfcX6PaW6DaWqDZWqDZW6DaX6PaZqfcaandaqndaandaKjcebXmlMjzMHrEGmOzFU+UAAAAAAAAAAAAAAAAAAAAAAAAAAAAFFmpPH/GZqXeq9v7h7/raqrda6vfbKzfbKzfa6vfa6vfaqrfaqrfa6vfa6vfbKzfbazfbKzfbKzef7nplMjzNn/GHWe3GFyqAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFFenOHzEWpzYnc31nM/1dLHhbqzfbq3fb63gb67gcK7gcK7gcK7gb67gb67gb67fdLLijsXwhLzsLnfDHGa3GFqpAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFVioJmu5RYvOd7LlpNT5lsryhb3qeLTjcbDgcbDgcrDgcrHgeLTjgbzpjsTwlcnyXZ7ZHWu7GWKzGFupAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFE2RGF6wMXnBRYvPY6Lcg7vqntD1otP5odL4oNH4n9D3lsvzdrHlT5LRJ3O/HGa3GF6xFU6SAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACCA7FVikF12xJWy6LHO/MXvEL3rELHfBKHXAJnO/JHC9Hmq5HGW2GF6xF1mkCSA7AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABA4aEkR+FlekF12vF12vF12vF12vGF2wGF6wF1ikEkR+BA4aAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:AAAAAAAAAAAAAA5y0f///////9FyDgAAAAAAAAAAAAAAAAAAAAAAASPT////////////////0yMBAAAAAAAAAAAAAAAAAAOZ/////////////////////5kDAAAAAAAAAAAAAAAF5v///////////////////////+YFAAAAAAAAAAAABeX//////////////////////////+UFAAAAAAAAAAXn/////////////////////////////+cFAAAAAAADnP///////////////////////////////5wDAAAAASn//////////////////////////////////ykBAAAG1v//////////////////////////////////1gYAABr/////////////////////////////////////GgADfP////////////////////////////////////98AwnW/////////////////////////////////////9YJEf///////////////////////////////////////xEV////////////////////////////////////////FRb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFdr/////////////////////////////////////2hURjf////////////////////////////////////+NEQky/////////////////////////////////////zIJAxvd///////////////////////////////////dGwMAEEz//////////////////////////////////0wQAAAGH7D///////////////////////////////+wHwYAAAENLuz/////////////////////////////7C4NAQAAAAMWOOv//////////////////////////+s4FgMAAAAAAAUZOu3////////////////////////tOhkFAAAAAAAAAAUZOLT/////////////////////tDgZBQAAAAAAAAAAAAUWLlrf////////////////31ouFgUAAAAAAAAAAAAAAAMNIDVMmd7////////emUw1IA0DAAAAAAAAAAAAAAAAAAEGEBspOEFDQ0NDQTgpGxAGAQAAAAAAAAAAAAAAAAAAAAAAAwkRFRYWFhYVEQkDAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    okImgStr = '32:32:AQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAO24ARYQARYYARIcARIcARIcARYgARokAR4oASIkASYYAPG8AAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAQHgAQ4YAS4wAiLY9qc1cxuF1xd9vudlgsNJQp8tBmMMwe64XZZ8ITIwASooAQnoAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAARIUAS4wAtNVy7/2t4fiR3PiB3Pl72/h52PZ21fNz1PFzzuxsu95Woso0hLYMZqAATI0ASokAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAQoYAeq0y9//A6v+c4P1+xehQrtYlm8cDk78AlMAAlMAAlMEAm8YFqtAiuNxFwOBfncYtc6oAWJUASosAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAQYQApMle9P+14/2Fy+xYm8YClMEAlsMAl8MAmMQAmMQAmMQAmMQAmMQAl8QAl8MAnMcEs9ZFsNRLfrIHZJ4ASYoAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAARIYAncVT5/me3/x9s9ssk8EAlsQAmMUAmcYAmcYAmcYAmcYAmcYAmcYAmcYAmcYAmcYAmMUAl8UAp88kuNlXg7UMZJ8ASooAAAAAAQAAAQAAAQAAAQAAAQAAAAAARIIAb6Uh2/CQ4Px8rtcllMMAl8YAmccAmccAmccAmccAmccAmccAmccAmccAmccAmccAmccAmccAmccAl8YApc8et9lXf7IHWJUASIUAAAAAAQAAAQAAAQAAAAAANmQAS4wAxeB13Pl+s9stlMQAl8YAmccAmccAmccAmccAmccAmccAmccAmccAmccAmccAmccAmccAmMcAmMcAmMcAl8YAp9Akr9NLc6oATY0ANmQAAAAAAQAAAQAAAAAARYYAkb0+0e11yuxZlMQAl8cAmcgAmcgAmcgAmcgAmcgAmcgAmcgAmcgAmcgAmcgAmcgAmMgAl8cAlMUAlMYAl8cAmMgAl8cAstdEmcUrZ6EASogAAAAAAQAAAQAAIDwAS4wAutpd2vZ3m8sDl8cAmckAmckAmckAmckAmckAmckAmckAmckAmckAmckAmckAmMkAlscAkMQA4fCz0eeMksYAl8gAmMkAnMsFt9lXfLABTY0AITwAAQAAAAAAQXsAcqcbvt5dw+ZNlccAmMoAmcoAmcoAmcoAmcoAmcoAmcoAmcoAmcoAmcoAmcoAmMoAlsgAj8UA3O2o////////pc8flcgAmMoAl8oAsNY+kb4gXpoAQ3wAAAAAAAAARoUAhLQmxuZkq9YjlsgAmcoAmcoAmcoAmcoAmcoAmcoAmcoAmcoAmcoAmcoAmMoAlsgAj8UA3O2n////////////+Pvsk8cAmMkAmMoApNEepc0+aaIASIcAAAAAAAAASIoAk78o0O5vnM0Fl8oAmcsAmcsAmcsAmMsAmMsAmcsAmcsAmcsAmcsAmMsAlskAj8YA3O6n////////////////3++vk8gAmMsAmMsAnMwFttlWdKoASowAAAAAAAAASIoAj7wfz+1vlcoAmMwAmcwAmcwAl8sAlMoAlMoAl8sAmMwAmcwAmMwAlsoAj8cA3O6n////////////////3O6nkMcAlssAmcwAmcwAl8wAutxdd6wASosAAAAAAAAASIoAhrYQy+prlssAmM0Amc0Al8wAksoA0eiM4fCzkMgAlssAmM0AlssAj8gA3O6n////////////////3O6nj8gAlssAmM0Amc0Amc0Al80Autxdd6wASosAAAAAAAAASYsAfbADx+VnlswAmM0AmM0AlcsApdQf////////3O6ojsgAk8oAjsgA3O6n////////////////3O6nj8gAlssAmM0Amc0Amc0Amc0Al80Autxdd6wASosAAAAAAAAASosAdqsAxOJkl80AmM4AmM4Ak8sA+Pzs////////////2+6jh8YA2+6j////////////////3O+nj8kAlswAmM4Amc4Amc4Amc4Amc4Al84Autxdd6wASosAAAAAAAAASowAdKoAu9tZm9AFmM8AmM8Ak8wA3/Cv////////////////////////////////////3O+nj8oAls0AmM8Amc8Amc8Amc8Amc8AmM8AnNEFttlWdKoASowAAAAAAAAAR4QAaKIAp8w9pdQemNAAmdAAls8AkMsA3O+n////////////////////////////3O+nj8sAls8AmNAAmdAAmdAAmdAAmdAAmdAAmNAApNQepc0+aaIAR4QAAAAAAAAAO20AXpoAkb0gsdg+l9AAmdAAmNAAls4Aj8sA3PCn////////////////////3PCnj8sAls4AmNAAmdAAmdAAmdAAmdAAmdAAmdAAmNAAr9g+kL0gXpoAO20AAAAAAAAAER8ATY0AfLABuNhXnNMFmNEAmdEAmNEAls8Aj8wA3PCn////////////3PCnj8wAls8AmNEAmdEAmdEAmdEAmdEAmdEAmdEAmNEAnNMFtthXfLABTY0AER8AAAAAAAAAAAAASIQAZ6AAmcUrstlEl9IAmdIAmdIAmNIAltAAj84A3vCs////3vCsj84AltAAmNIAmdIAmdIAmdIAmdIAmdIAmdIAmdIAl9IAsNlEmMUrZ6AASIQAAAAAAAAAAQAAAAAAHTYATY0Ac6oAr9NLp9Ykl9MAmdMAmdMAmNMAltIAk9AAkdAAk9AAltIAmNMAmdMAmdMAmdMAmdMAmdMAmdMAmdMAl9MAptYkrtNLdKoATY0AHTYAAAAAAQAAAQAAAAAAAAAAP3YAWJUAf7EHt9hXpNYel9MAmdMAmdMAmdMAmNMAmNIAmNMAmdMAmdMAmdMAmdMAmdMAmdMAmdMAmdMAmNMApNYetthXf7EHWJUAP3YAAAAAAAAAAQAAAQAAAAAAAAAAAAAASIcAZJ4Ag7UMt9hXp9ckl9UAmNQAmdQAmdQAmdQAmdQAmdQAmdQAmdQAmdQAmdQAmdQAmNQAmNUAptcktthXg7UMZJ4ASIcAAAAAAAAAAAAAAQAAAQAAAQAAAAAAAAAAAAAAR4cAZJ4Af7IHrtNLsdpEnNcFmNYAmNUAmNUAmdUAmdUAmdUAmdUAmNUAmNUAmNYAnNcFsNpErtNLf7IHZJ4AR4cAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAASIcAWJUAdKoAmcQrtthXsNo+pNgenNcFl9cAl9cAl9cAl9cAnNcFpNger9o+tthXmMQrdKoAWJUASIcAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAP3QATY0AZ6AAfLABkL0gpcw+tthXuttdudtdudtdudtdtthXpcw+kL0gfLABZ6AATY0AP3QAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAGi8AR4MATY0AXpoAaaIAdKoAd6wAd6wAd6wAd6wAdKoAaaIAXpoATY0AR4MAGi8AAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAACxUANmUARoIASowASosASosASosASosASowARoIANmUACxUAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAA:AAAAAAAAAAAAAA5y0f///////9FyDgAAAAAAAAAAAAAAAAAAAAAAASPT////////////////0yMBAAAAAAAAAAAAAAAAAAOZ/////////////////////5kDAAAAAAAAAAAAAAAF5v///////////////////////+YFAAAAAAAAAAAABeX//////////////////////////+UFAAAAAAAAAAXn/////////////////////////////+cFAAAAAAADnP///////////////////////////////5wDAAAAASn//////////////////////////////////ykBAAAG1v//////////////////////////////////1gYAABr/////////////////////////////////////GgADfP////////////////////////////////////98AwnW/////////////////////////////////////9YJEf///////////////////////////////////////xEV////////////////////////////////////////FRb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFdr/////////////////////////////////////2hURjf////////////////////////////////////+NEQky/////////////////////////////////////zIJAxvd///////////////////////////////////dGwMAEEz//////////////////////////////////0wQAAAGH7D///////////////////////////////+wHwYAAAENLuz/////////////////////////////7C4NAQAAAAMWOOv//////////////////////////+s4FgMAAAAAAAUZOu3////////////////////////tOhkFAAAAAAAAAAUZOLT/////////////////////tDgZBQAAAAAAAAAAAAUWLlrf////////////////31ouFgUAAAAAAAAAAAAAAAMNIDVMmd7////////emUw1IA0DAAAAAAAAAAAAAAAAAAEGEBspOEFDQ0NDQTgpGxAGAQAAAAAAAAAAAAAAAAAAAAAAAwkRFRYWFhYVEQkDAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    checkImgStr = '32:32:////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////AAAASnqoRXemRHamRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRXemRHamRXemSHelAAAAAAAA////////////AAAARHem6fH7r8fjscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkscjkr8fj6fH7RHemAAAAAAAA////////////AAAAQnWl4ev3VIfCVIjDU4fDUobDUobDUobDUobDUobDUobDUobDUobDUobDUobDUobDUobDUobDUobDUobDUobDU4fDVIjDVIfC4ev3QnWlAAAAAAAA////////////AAAAQnWl2ub1VInE8Onj6ubi6OXi6OXi6OXi6OXi6OXi6OXi6OXi6OXi6OXi6OXi6OXi6OXi6OXi6OXi6eXj6ubk6+bl8erkVIrF2ub1QnWlAAAAAAAA////////////AAAAQnWl1ePzVYrG7Ojk4+Lj4eHi4eHi4eHi4eHi4eHi4eHi4eHi4eHi4eHi4eHi4eHi4eHi4eHj4uLk5OPo6eXv7Obx7+nqVYvI1ePzQnWlAAAAAAAA////////////AAAAQ3Wl0ODyV4zJ7Onl4+Pj4eLj4eLj4eLj4eLj4eLj4eLj4eLj4eLj4eLj4eLj4eLj4eLj4uLk5eTp7uj4hLtPQKAA9u31WI3L0ODyQ3WlAAAAAAAA////////////AAAAQ3Wlyt3xWJDK7enn5OTl4uPl4uPl4uPl4uPl4uPl4uPl4uPl4uPl4uPl4uPl4uPl4+Pm5uXs7+n7irxVTqMAS6IA+/D9WpHNyt3xQ3WlAAAAAAAA////////////AAAAQ3Wlx9vvWpPM7+zo5ubm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5eXn6Oft8ev8irtWUaEAV6QDT6AA/vL/XZTQx9vvQ3WlAAAAAAAA////////////AAAARHWlwtnvXZXP8e7q6Ojo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5+fp6unv8+7+jbtXVKAAW6QGW6MGUZ8A//X/X5bSwtnvRHWlAAAAAAAA////////////AAAARHWlvtbvYJnR9O/t6+rt6ejs6Ojr6Ojq6Ojq6Ojq6Ojq6Ojq6Ojq6ejs7Orx9u//jbtXVZ4AXKEGXqMJW6EET5sA//X/YZrUvtbvRHWlAAAAAAAA////////////AAAARHWludTuY5zU+PPz9PD68e/47Ozx6urs6err6err6err6err6urs7ezy9vH/kLpYVZ0AXaAGX6IJXaAGVZwAj7pU/fX7Y5zVudTuRHWlAAAAAAAA////////////AAAARHaltdLtZp7Y//n/SJIAjLdR+PT/7+/07Ozv6+zt6+zt7Ozv7+/0+fT/kLpXWJoAX54GYZ8JX54GWJoAkLpY+vT/+vX1ZZ7WtdLtRHalAAAAAAAA////////////AAAARXalsdHuaaLb//v/U5YAVpgAkbpZ+/X/8e/17u3v7u3v8e/1+/X/kbpZWJkAYJ0GYp8JYJ0GWJkAkblY+vT/8/D1+vTxZ6HYsdHuRXalAAAAAAAA////////////AAAARXalrc7tbKXe//7/V5UAX5oBWZcAk7hZ/ff/9PL49PL4/ff/k7hZWZcAYZsFY50IYZsFWZcAk7lY/ff/8/H38vHy+/byaqTarc7tRXalAAAAAAAA////////////AAAARXalqs3ubqfg////WZMAY5kFY5kFW5UAlbla//z///z/lblaW5UAY5kFZZoIY5kFW5QAlbhZ/fn/9PT48fHy8vLx/PjzbKbcqs3uRXalAAAAAAAA////////////AAAARXalpczucKvi////V5AAY5cDZpoIZJgFXpQAnb1knb1kXpQAZJgFZpoIZJgFXJMAlrha//r/9vT68/L08vLz9PPz/vj1b6nepczuRXalAAAAAAAA////////////AAAARXalo8vvcq3i////mLdWXZAAZZYFZ5cIZpYGY5UCY5UCZpYGZ5cIZZYFXZEAmLha//3/+Pf89fT39PT19PT19vX1//r3cazgo8vvRXalAAAAAAAA////////////AAAARXaln8ruc67i///+////mbdbX5AAZ5UFaZcJapcJapcJaZcJZ5UFX5AAmbdb////+fn99vb39fb29fb29fb29/f2//z4cq7hn8ruRXalAAAAAAAA////////////AAAARnalncnvdbLj//77/fv/////mrdbYI0AaJMFa5UJa5UJaJMFYI0Amrdb////+/r/+Pf69/f49/f49/f49/f4+fj4//36dbLjncnvRnalAAAAAAAA////////////AAAARnalmsnxd7Tm///7/Pv7/fz/////nLdcYYsAaZAEaZAEYYsAnLdc/////fz/+vn6+fn5+fn5+fn5+fn5+fn5+/r5///7d7TmmsnxRnalAAAAAAAA////////////AAAARnaklsnyerbo///9/fz7/Pz8//7/////nbVbYYgAYYgAnbVb//////7//Pz8+/v7+/v7+/v7+/v7+/v7+/v7/fz7///9erbolsnyRnakAAAAAAAA////////////AAAARnaklcnzfbjq///////+/v79////////////mrJTmrJT/////////////v79/v79/v79/v79/v79/v79/v79///+////fbjqlcnzRnakAAAAAAAA////////////AAAARnakk8n1gr3t////////////////////////////////////////////////////////////////////////////////gr3tk8n1RnakAAAAAAAA////////////AAAAR3akk8v3i8PxhMDvgb7vgb7ugb7ugb7vgb7vgr7wgr7wgb7vgb7vgb7ugb7ugb7ugb7ugb7ugb7ugb7ugb7ugb7vhMDvi8Pxk8v3R3akAAAAAAAA////////////AAAASHimmtL+lc35lMz5k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4k8z4lMz5lc35mtL+SHimAAAAAAAA////////////AAAAQ26YSHimR3akRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkRnWkR3akSHimQ26YAAAAAAAA////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABfD///////////////////////////////+0BAAAAAAQ//////////////////////////////////8NAAAAABb//////////////////////////////////xUAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAVxP///////////////////////////////8QVAAAAAA0rP0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0M/Kw0AAAAABA0VFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhUNBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    uncheckImgStr = '32:32:////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////AAAAlaS3kaK1j5+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zjp+zj5+zkaK1kqG0AAAAAAAA////////////AAAAkaK1////////////////////////////////////////////////////////////////////////////////////////////////kaK1AAAAAAAA////////////AAAAj6Cz////////////////////////////////////////////////////////////////////////////////////////////////j6CzAAAAAAAA////////////AAAAj5+z/////f7++/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9+/z9/f7+////j5+zAAAAAAAA////////////AAAAj6Cz/////P39+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8+vv8/P39////j6CzAAAAAAAA////////////AAAAkKC0/P7++vz8+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+Pr7+vz8/P7+kKC0AAAAAAAA////////////AAAAkKC0+Pz8+Pr99vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj79vj7+Pr9+Pz8kKC0AAAAAAAA////////////AAAAkKC09fj79vn89Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69Pf69vn89fj7kKC0AAAAAAAA////////////AAAAkKC08vb49Pf78vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX58vX59Pf78vb4kKC0AAAAAAAA////////////AAAAkaG07/P38/b68fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48fT48/b67/P3kaG0AAAAAAAA////////////AAAAkaG07PH18fX57/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P37/P38fX57PH1kaG0AAAAAAAA////////////AAAAkaG06O/z7/P47fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27fH27/P46O/zkaG0AAAAAAAA////////////AAAAkaG15e3y7fL36/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D16/D17fL35e3ykaG1AAAAAAAA////////////AAAAkqK14+rv6/H26e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06e/06/H24+rvkqK1AAAAAAAA////////////AAAAkqK13+fu6+/26O306O306O306O306O306O306O306O306O306O306O306O306O306O306O306O306O306O306O306O306+/23+fukqK1AAAAAAAA////////////AAAAkqK13OXs6e715uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz5uzz6e713OXskqK1AAAAAAAA////////////AAAAk6K12eLp5+305Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5Ovy5+302eLpk6K1AAAAAAAA////////////AAAAk6K11eDo5evz4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx4unx5evz1eDok6K1AAAAAAAA////////////AAAAk6O1097m4+ry4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4Ojw4+ry097mk6O1AAAAAAAA////////////AAAAk6O1z9vl4ujx3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv3+bv4ujxz9vlk6O1AAAAAAAA////////////AAAAlKO2zNni4Ofw3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu3eXu4OfwzNnilKO2AAAAAAAA////////////AAAAlKO2ytfh3ubv2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt2+Tt3ubvytfhlKO2AAAAAAAA////////////AAAAlKO2xtTf3OXw2uLu2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2eLt2uLu3OXwxtTflKO2AAAAAAAA////////////AAAAlKS3xNLf3Obw2uTv2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTu2uTv3ObwxNLflKS3AAAAAAAA////////////AAAAlqW3xdPfwtDcwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwc/cwtDcxdPflqW3AAAAAAAA////////////AAAAiZamlqW3laS3lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2lKS2laS3lqW3iZamAAAAAAAA////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABfD///////////////////////////////+0BAAAAAAQ//////////////////////////////////8NAAAAABb//////////////////////////////////xUAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAVxP///////////////////////////////8QVAAAAAA0rP0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0M/Kw0AAAAABA0VFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhUNBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='

    # noinspection SpellCheckingInspection
    emptyImgStr = '32:32:////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////:////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////'

    # noinspection SpellCheckingInspection
    stopImgStr = '32:32:AQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAwTkowTcnwDcnwTgowTgowTkpwTkpwTopwToqwToqwToqwTsrwjsrwTwsAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjQl4J2U7sO966yi6qif6KWa56CV5puR5ZiN4pOI446D4Yt+34V53YuA0XBkwDkqAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjQk4KCZ77645EIm5D0f5D4h5D8h5D8i5EAi5UAi5UAj5UEj5UEk5UEj5UQn3IB00GxgwDoqAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjQk4KCZ8MO95UUr5UMm5UYq5UYq5Ucq5Ucq5Ucq5Ucq5Ucq5Ucq5Ucr5Ucq5kUp5kYr2nxvz2ldwDoqAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvjQl35qT7r+55kgt5kUp5kku5kov5kov5kov5kov5kov5kov5kov5kov5kov5kov5kov50gs50ku2XhqzWVYwDoqAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAvzUl3JWM7bmx50ov50cr50sw50wx50wx50wx50wx50wx50wx50wx50wx50wx50wx50wx50wx50wx6Eov50sx13NlzGBVwDsrAAAAAQAAAQAAAQAAAQAAAQAAAAAAvzYm25CI67Gq6Uwx6Eou6E0y6E4z6E4z6E4z6E4z6E4z6E4z6E4z6E4z6E4z6E4z6E4z6E4z6E4z6E4z6E4y6Uwx6U4y1W1fy11QwDwsAAAAAQAAAQAAAQAAAAAAvzYn2YqC6ayj6k806Uwx6U816VA26VA26VA26VA26VA26VA26VA26VA26VA26VA26VA26VA26VA26VA26VA26VA26VA26k806U811GhaylhLwTwsAAAAAQAAAAAAwDoq2IZ856Wc6lA36k8z6lE36lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI46lI461E261I40mFUyVRGwT4uAAAAAAAAwTgn5bOs7FI361E161M561Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q661Q67VQ57VM6zF9Twz0tAAAAAAAAwTcn4q2m7lA17FQ77FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97FY97VY98FY8yl1Rwj0tAAAAAAAAwTgn4aii71M47Vc+7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/7Vg/8Vg+yFtOwz0tAAAAAAAAwTgo36Ob8FU77llA7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB7lpB71pB8ltBx1hLwz4uAAAAAAAAwTgo3p2W8Vg/71tD71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE71xE8FxE811Ex1VHwz4uAAAAAAAAwTko25eQ81tB8F1F8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8F5G8V5G9GBHxVNFwz4uAAAAAAAAwTkp2pGJ9FxE8V5H8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8V9I8l9I9WFJxU9Cwz4uAAAAAAAAwTop14yE9l9I82FK82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL82FL9GFL+GNNxEw+wz4uAAAAAAAAwToq1oZ+92FK9GNM9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9GNN9WNN+WZPwkg6wz4uAAAAAAAAwjoq04F4+WRN9WVO9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9WVP9mVP+mhRwUU2wz8vAAAAAAAAwjsq0ntw+mdQ92dS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS9mdS92hT/GtVwEExwz8vAAAAAAAAwjsr0XVr+WpV+WlU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU92lU+WtW+2xXwD8vxD8vAAAAAAAAvjwszF1Q2G9i+WxX+mtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+GtW+m1Y+mxYy0Y2wj8vvz4vAAAAAAAAAAAAujoqylpN1mxf+m9a+25Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+W1Z+29b+25aykc2wT8vvD0tAAAAAAAAAAAAAAAAAAAAujoqyVhJ1Wha/HBd/HBc+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b+m9b/HFd/XFcy0c2wT4vuz0tAAAAAAAAAAAAAQAAAAAAAAAAAAAAujsqyFRH02NW/XJe/XJe+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd+3Fd/XNf/nNfy0c2wT4vuz0tAAAAAAAAAAAAAQAAAQAAAQAAAAAAAAAAAAAAujsrx1FD0l9R/nRh/nVi/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/HNg/nVi/3Riy0Y3wT4uuz0tAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAujsrxU0+0VtM/3Zk/3dk/nZj/nZj/nZj/nZj/nZj/nZj/nZj/nZj/nZj/nZj/3hk/3Zky0g3wT4uuz0tAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAuzsrxEk70FZH/3po/3xp/3xp/3xp/3xp/3xp/31p/31p/31q/31q/31q/3poy0g3wT4uuz0tAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAuzwsxEc3xEk6w0g5wkY4wkU3wEQ2wEEzv0Ayvz8vvz0tvjssvjwsvz0twj8vuz0tAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAvz0uwz4uwz4uwz4uwz4uwz4uwz4uwz4uwz8vwz8vwz8vwz8vwz8vvz4vAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAA:AAAAAAAAAAAF6f///////////////+kFAAAAAAAAAAAAAAAAAAAABeX//////////////////+UFAAAAAAAAAAAAAAAAAAXl/////////////////////+UFAAAAAAAAAAAAAAAF5f///////////////////////+UFAAAAAAAAAAAABeX//////////////////////////+UFAAAAAAAAAAXl/////////////////////////////+UFAAAAAAAF5f///////////////////////////////+UFAAAABeX//////////////////////////////////+UFAAXq/////////////////////////////////////+oFEP///////////////////////////////////////xAW////////////////////////////////////////Fhb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFv///////////////////////////////////////xYW////////////////////////////////////////Fhb///////////////////////////////////////8WFu7/////////////////////////////////////7hYQNev//////////////////////////////////+s1EAUZOuv////////////////////////////////rOhkFAAUZOev/////////////////////////////6zkZBQAAAAUZOev//////////////////////////+s5GQUAAAAAAAUZOev////////////////////////rORkFAAAAAAAAAAUZOev/////////////////////6zkZBQAAAAAAAAAAAAUZOev//////////////////+s5GQUAAAAAAAAAAAAAAAUZOu/////////////////vOhkFAAAAAAAAAAAAAAAAAAUZNUJDQ0NDQ0NDQ0NDQjUZBQAAAAAAAAAAAAAAAAAAAAUQFhYWFhYWFhYWFhYWEAUAAAAAAAAAAA=='
    def __init__(self, size: wx.Size):
        self.image_list = wx.ImageList(size.GetWidth(), size.GetHeight())
        self.size = size
        self._names = {}

        self.add_from_base64(self.BuiltInImage.CRITICAL, self.criticalImgStr)
        self.add_from_base64(self.BuiltInImage.ERROR, self.errorImgStr)
        self.add_from_base64(self.BuiltInImage.WARNING, self.warningImgStr)
        self.add_from_base64(self.BuiltInImage.INFO, self.infoImgStr)
        self.add_from_base64(self.BuiltInImage.OK_CHECK, self.okImgStr)
        self.add_from_base64(self.BuiltInImage.CHECK_SYMBOL, self.checkImgStr)
        self.add_from_base64(self.BuiltInImage.UNCHECK_SYMBOL, self.uncheckImgStr)
        self.add_from_base64(self.BuiltInImage.EMPTY, self.emptyImgStr)
        self.add_from_base64(self.BuiltInImage.STOP, self.stopImgStr)

    def add(self, img_name: Union[str, Enum], img: Union[wx.Bitmap, wx.Image, str]):
        if img_name in self._names.keys():
            mlogger.error(f'{self} Имя {img_name} уже добавлено')
            return

        if type(img) == str:
            if os.path.exists(img):
                img_src: wx.Image = wx.Image(img, wx.BITMAP_TYPE_ANY)
                scaled_image = img_src.Scale(self.size.GetWidth(), self.size.GetHeight(), wx.IMAGE_QUALITY_BICUBIC)
                bmp = scaled_image.ConvertToBitmap()
                self._names[img_name] = self.image_list.Add(bmp)
        elif type(img) == wx.Bitmap:
            img_size: wx.Size = img.GetSize()
            if img_size.GetWidth() != self.size.GetWidth() or img_size.GetHeight() != self.size.GetHeight():
                new_image = img.ConvertToImage()
                scaled_image: wx.Image = new_image.Scale(self.size.GetWidth(), self.size.GetHeight(), wx.IMAGE_QUALITY_BICUBIC)
                new_bitmap = scaled_image.ConvertToBitmap()
            else:
                new_bitmap = img
            self._names[img_name] = self.image_list.Add(new_bitmap)

        elif type(img) == wx.Image:
            scaled_image: wx.Image = img.Scale(self.size.GetWidth(), self.size.GetHeight(), wx.IMAGE_QUALITY_BICUBIC)
            new_bitmap = scaled_image.ConvertToBitmap()
            self._names[img_name] = self.image_list.Add(new_bitmap)
        else:
            mlogger.error(f'{self}  объект {img} не допустимо добавлять')
            return


    def add_from_file_name(self, img_name: Union[str, Enum], file_name: str):
        if os.path.exists(file_name):
            img = wx.Image(file_name, wx.BITMAP_TYPE_ANY)
            self.add(img_name, img)

    def add_from_base64(self, img_name: Union[str, Enum], img_base64str: str):
        img = _base64_str_to_image(img_base64str)
        img = img.Scale(self.size.GetWidth(), self.size.GetHeight(), wx.IMAGE_QUALITY_BICUBIC)
        bmp = img.ConvertToBitmap()
        self.add(img_name, bmp)

    def get(self, img_name: Union[str, Enum], img_type: Type)->Optional[Union[wx.Icon, wx.Bitmap]]:
        if img_name not in self._names.keys():
            mlogger.error(f'{self}  объект с именем {img_name} не найден')
            return None
        index = self._names[img_name]
        if img_type == wx.Icon:
            return self.image_list.GetIcon(index)
        elif img_type == wx.Bitmap:
            return self.image_list.GetBitmap(index)
        else:
            mlogger.error(f'{self}  Объект типа {img_type} невозможно вернуть')
        return None

    def get_index(self, img_name: Union[str, Enum], no_image_not_found: bool = False):
        if img_name not in self._names.keys():

            if not no_image_not_found:
                mlogger.error(f'{self}  объект с именем {img_name} не найден')
                return None
            else:
                return -1
        return self._names[img_name]



    def count(self):
        return self.image_list.GetImageCount()

class GuiWidgetSettings:
    grid_header_icon_size: int = 16
    grid_popup_icon_size: int = 20
    datetime_icon_size: int = 18
    menu_bitmap_size: wx.Size = wx.Size(24, 24)
    listctrl_bitmap_size = menu_bitmap_size
    notebook_page_bitmap_size = wx.Size(24, 24)
    table_bitmap_size = wx.Size(24, 24)
    file_dialog_bitmap_size = wx.Size(24, 24)
    statusbar_bitmap_size = wx.Size(20,20)
    treectrl_bitmap_size =wx.Size(20,20)

    date_format_str = '%d.%m.%Y'
    date_time_format_str = '%d.%m.%Y %H:%M:%S'

class BasicPanel(wx.Panel, BasicWxCommandListener, WxEvents):
    _parent: Any
    def __init__(self, parent: Union[wx.Panel, wx.Frame, wx.Window], style:int=wx.NO_BORDER | wx.TAB_TRAVERSAL):
        self._parent = parent
        wx.Panel.__init__(self, parent, style=style)
        BasicWxCommandListener.__init__(self, self)
        WxEvents.__init__(self)
        #if parent:
        #    self.copy_from(parent)
        #WxEvents.__init__(self)
        # DOESN'T WORK FOR PANELS!!!!
        # self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)

class BasicPopupMenu(wx.Menu):
    _menu_item_list: Dict[int, Union[wx.MenuItem, wx.Menu]]
    _commands: Dict[int, Optional[WxCommand]]
    def __init__(self):
        wx.Menu.__init__(self)
        self._commands: Dict[int, WxCommand] = {}
        self._menu_item_list: Dict[int, wx.MenuItem] = {}

    def get_commands_ids(self):
        return list(self._commands.keys())

    def get_wxcommand(self, cmd_id:int)->Optional[WxCommand]:
        if cmd_id in self._commands.keys():
            return self._commands[cmd_id]
        return None

    def get_menu_item(self, cmd_id: int)->Optional[Union[wx.MenuItem, wx.Menu,]]:
        if cmd_id in self._menu_item_list.keys():
            return self._menu_item_list[cmd_id]
        return None


    def add_submenu(self, menu_name:str, sub_menu: wx.Menu, sub_menu_id:int, pos: Optional[int]=None):
        if pos is not None:
            if not 0<=pos<self.GetMenuItemCount():
                pos = self.GetMenuItemCount()
        else:
            pos = self.GetMenuItemCount()
        if sub_menu_id in self._commands.keys():
            mlogger.warning(f'{self} добавить подменю {menu_name} id={sub_menu_id}, такой id уже существует')
        else:
            self.Insert(pos,sub_menu_id, menu_name,sub_menu)
            self._commands[sub_menu_id] = None
            self._menu_item_list[sub_menu_id] = sub_menu


    def add_item(self, cmd: WxCommand, pos: Optional[int]=None):
        if pos is not None:
            if not 0<=pos<self.GetMenuItemCount():
                pos = self.GetMenuItemCount()
        else:
            pos = self.GetMenuItemCount()
        if cmd.iid in self._commands.keys():
            mlogger.warning(f'{self} невозможно добавить в меню элемент id={cmd.iid}. Такой уже существует')
            return
        if cmd.help_string:
            new_menu_item: wx.MenuItem = self.Insert(pos, cmd.iid, cmd.name, cmd.help_string)
        else:
            new_menu_item: wx.MenuItem = self.Insert(pos, cmd.iid, cmd.name)
        if cmd.execute is not None:
            self.Bind(wx.EVT_MENU, cmd.execute, id=cmd.iid)

        if cmd.Image is not None:
            new_menu_item.SetBitmap(cmd.Bitmap)

        self._commands[cmd.iid] = cmd
        self._menu_item_list[cmd.iid] = new_menu_item
        if not cmd.can_execute():
            new_menu_item.Enable(False)
        if __debug__:
            mlogger.debug(f'{self} добавление меню {self.GetTitle()} пункта {cmd.name}')


    def clear_items(self):
        for cmd_id in self.get_commands_ids():
            self.delete_item_by_id(cmd_id)


    def delete_item_by_id(self, cmd_id: int):
        if cmd_id in self._menu_item_list.keys():
            if type(self._menu_item_list[cmd_id]) == wx.MenuItem:
                self.delete_item(self._commands[cmd_id])
            elif type(self._menu_item_list[cmd_id]) == wx.Menu:
                self.Remove(cmd_id)
                del self._menu_item_list[cmd_id]
                del self._commands[cmd_id]
        else:
            mlogger.warning(f'{self} невозможно удалить из меню элемент id={cmd_id}. Не найден')


    def delete_item(self, cmd: WxCommand):
        if cmd.iid in self._menu_item_list.keys():
            self.Remove(self._menu_item_list[cmd.iid])
            del self._menu_item_list[cmd.iid]
            del self._commands[cmd.iid]
            if __debug__:
                mlogger.debug(f'{self} из меню {self.GetTitle()} пункт {cmd.name} удален')
        else:
            mlogger.warning(f'{self} невозможно удалить из меню {self.GetTitle()} пункт {cmd.name}. Не найден')

    def add_separator(self):
        if __debug__:
            mlogger.debug(f'{self} добавление разделителя меню {self.GetTitle()}')
        self.AppendSeparator()

    def add_item_with_handler(self,  name: str, handler:Callable, iid:Optional[int]=None, params:Tuple = None, checked: Optional[bool] = None, radio: bool = False):
        if iid is None:
            iid = wx.ID_ANY
        if checked is None:
            new_menu_item: wx.MenuItem = wx.MenuItem(self, iid, name, kind=wx.ITEM_NORMAL)
            self.Append(new_menu_item)
        else:
            if not radio:
                new_menu_item: wx.MenuItem = wx.MenuItem(self, iid, name, kind = wx.ITEM_CHECK)
            else:
                new_menu_item: wx.MenuItem = wx.MenuItem(self, iid, name, kind=wx.ITEM_RADIO)
            self.Append(new_menu_item)
            new_menu_item.Check(checked)

        if params is not None:
            self.Bind(wx.EVT_MENU, lambda cur_evt, param=params: handler(cur_evt, *params), new_menu_item)
        else:
            self.Bind(wx.EVT_MENU, handler, new_menu_item)

    def add_item_simple(self, name: str, handler:Callable, iid:Optional[int]=None, checked: Optional[bool] = None, radio: bool = False):
        if iid is None:
            iid = wx.ID_ANY
        if checked is None:
            new_menu_item: wx.MenuItem = wx.MenuItem(self, iid, name, kind=wx.ITEM_NORMAL)
            self.Append(new_menu_item)
        else:
            if not radio:
                new_menu_item: wx.MenuItem = wx.MenuItem(self, iid, name, kind = wx.ITEM_CHECK)
            else:
                new_menu_item: wx.MenuItem = wx.MenuItem(self, iid, name, kind=wx.ITEM_RADIO)
            self.Append(new_menu_item)
            new_menu_item.Check(checked)

        self.Bind(wx.EVT_MENU, handler, new_menu_item)

    def get_count(self):
        return len(self._menu_item_list)+len(self._commands)

class BasicMenu(wx.MenuBar):
    _menu_positions: Dict[int, int]
    _menus: Dict[int, BasicPopupMenu]
    _menu_items: Dict[int, wx.MenuItem]
    _commands: Dict[int, WxCommand]
    _parent: wx.Frame
    _parent: Any
    def __init__(self, parent: wx.Frame):
        self._parent = parent
        wx.MenuBar.__init__(self)
        self._parent = parent
        self._commands: Dict[int, WxCommand] = {}
        self._menu_positions = {}
        self._menus = {}
        self._menu_items = {}
        self._parent.SetMenuBar(self)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)


    def on_destroy(self, evt: wx.WindowDestroyEvent):
        if evt.GetWindow().__class__.__name__ == self.__class__.__name__:
            self._commands.clear()
            self._menu_positions.clear()
            self._menus.clear()
            self._menu_items.clear()
            mlogger.debug(f'Destroyed {self}')


    def add_menu(self, menu: BasicPopupMenu, name: str, menu_id: int, pos: Optional[int]=None):
        if menu_id in self._menu_positions.keys():
            mlogger.warning(f'{self} невозможно добавить {name} id={menu_id}, такой id уже существует')
            return

        can_add = True
        for cmd_id in menu.get_commands_ids():
            if cmd_id not in self._commands.keys():
                self._commands[cmd_id] = menu.get_wxcommand(cmd_id)
                self._menu_items[cmd_id] = menu.get_menu_item(cmd_id)
            else:
                mlogger.warning(f'{self} невозможно добавить {name} id={menu_id}, такой id уже существует')
                can_add = False
        if can_add:

            if pos:
                if not 0<=pos<=self.GetMenuCount():
                    pos = self.GetMenuCount()
            else:
                pos = self.GetMenuCount()
            self._menus[menu_id] = menu
            for i, j in self._menu_positions.items():
                if j>= pos:
                    self._menu_positions[i]=j+1
            self._menu_positions[menu_id] = pos

            self.Insert(pos, menu, name)


    def delete_menu(self, menu_id: int):
        if menu_id in self._menus.keys() and menu_id in self._menu_positions.keys():
            for cmd_id in self._menus[menu_id].get_commands_ids():
                if cmd_id in self._commands.keys():
                    del self._commands[cmd_id]
                    del self._menu_items[cmd_id]
            old_pos = self._menu_positions[menu_id]

            for i,j in self._menu_positions.items():
                if j>old_pos:
                    self._menu_positions[i] = j-1
            self.Remove(self._menu_positions[menu_id])
            del self._menus[menu_id]
            del self._menu_positions[menu_id]

        else:
            mlogger.warning(f'{self} невозможно удалить id={menu_id}, такой id не найден')
            return



    def update_wxcommand_states(self):
        cmd: WxCommand
        for cmd in self._commands.values():
            if cmd is not None:
                self.update_menu_item_state(cmd, cmd.can_execute())
        if __debug__:
            mlogger.debug(f'{self} обновление статусов команд')

    def update_menu_item_state(self, cmd: WxCommand, state:bool):
        if cmd.iid in self._menu_items.keys():
            menu_item : wx.MenuItem = self._menu_items[cmd.iid]
            menu_item.Enable(state)
            if menu_item.IsCheckable():
                menu_item.Check(cmd.checked)
        else:
            mlogger.warning(f'{self} невозможно обновить {cmd.name}, id={cmd.iid} не найден')



class BasicStatusBar(wx.StatusBar):
    image_ok = None
    image_info = None
    image_verbose = None
    image_warning = None
    image_debug = None
    image_error = None

    ID_OK = 1
    ID_ERROR = 2
    ID_WARNING = 3
    ID_INFO = 4
    ID_VERBOSE = 5
    ID_DEBUG = 6

    _static_bitmaps: Dict[int, Optional[wx.StaticBitmap]] = {}
    _bitmap_names: Dict[int, Optional[str]] = {}
    #size_changed: bool = False
    click_panel_callback: Optional[Callable[[int],None]]
    _parent: Any
    _image_list: ImageList
    def __init__(self, parent, style=wx.STB_SIZEGRIP):
        self._parent = parent
        wx.StatusBar.__init__(self, parent, style)
        self.click_panel_callback = None
        self._bitmap_names = {}
        self._static_bitmaps = {}
        self._image_list = ImageList(GuiWidgetSettings.statusbar_bitmap_size)
        #self.image_ok = wx.Bitmap(runPath + "\\Icons\\StatusBar\\ok.ico", wx.BITMAP_TYPE_ANY)
        #self.image_info = wx.Bitmap(runPath + "\\Icons\\StatusBar\\info.ico", wx.BITMAP_TYPE_ANY)
        #self.image_verbose = wx.Bitmap(runPath + "\\Icons\\StatusBar\\verbose.ico", wx.BITMAP_TYPE_ANY)
        #self.image_warning = wx.Bitmap(runPath + "\\Icons\\StatusBar\\warning.ico", wx.BITMAP_TYPE_ANY)
        #self.image_debug = wx.Bitmap(runPath + "\\Icons\\StatusBar\\debug2.ico", wx.BITMAP_TYPE_ANY)
        #self.image_error = wx.Bitmap(runPath + "\\Icons\\StatusBar\\error.ico", wx.BITMAP_TYPE_ANY)

        # This status bar has three fields
        self.SetFieldsCount(1)
        #self.SetStatusWidths([0, 30, 400])

        #self.size_changed = False
        # self.Bind(wx.EVT_SIZE, self.OnSize)
        # self.Bind(wx.EVT_IDLE, self.OnIdle)

        #self.SetStatusText("...", 1)

        # This will fall into field 1 (the second field)
        #bmp = self.image_ok
        #self.bmpbtn = wx.StaticBitmap(self, -1, self.image_ok, (1, 1), (34, 34))

        # self.bmpbtn = wx.BitmapButton(self, id = wx.ID_ANY, bitmap = bmp,size = (bmp.GetWidth()+1, bmp.GetHeight()+1))
        # self.bmpbtn.Bind(wx.EVT_BUTTON, self.OnStatusClick)
        # self.bmpbtn.SetWindowStyleFlag(wx.NO_BORDER)

        # set the initial position of the checkbox
        self.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_click)
        #self.reposition()

    def add_bitmap(self, name: str, img: Union[wx.Bitmap, wx.Image, str]):
        self._image_list.add(name, img)

    def is_bitmap_exists(self, name:str):
        return self._image_list.get_index(name, True)>=0


    def _on_mouse_click(self, evt: wx.MouseEvent):
        if evt.GetEventObject() == self:
            for i in range(self.GetFieldsCount()):
                rect: wx.Rect = self.GetFieldRect(i)
                if rect.Contains(evt.GetPosition()):
                    if self.click_panel_callback:
                        self.click_panel_callback(i)
        elif type(evt.GetEventObject()) == wx.StaticBitmap:
            bmp: wx.StaticBitmap = evt.GetEventObject()
            bmp_name = bmp.GetName().split('_')
            if len(bmp_name) == 2:
                if self.click_panel_callback:
                    self.click_panel_callback(int(bmp_name[1]))

        evt.Skip()

    def set_panel_text(self, text:str, panel_number: int):
        if panel_number >= self.GetFieldsCount() and panel_number>=0:
            self.SetFieldsCount(panel_number+1)
        self.SetStatusText(text,panel_number)
        #self.reposition()
        #if __debug__:
        #    mlogger.debug('BasicStatusBar для панели {0} установка текста: {1}'.format(panel_number, text))


    def set_panel_bitmap_hint(self,hint_str: str, panel_number:int):
        if panel_number in self._static_bitmaps.keys():
            st_bitmap: Optional[wx.StaticBitmap] = self._static_bitmaps[panel_number]
            if st_bitmap is not None:
                st_bitmap.SetToolTip(hint_str)

    def set_panel_bitmap(self, bitmap_name: Optional[str], panel_number: int, align: int = wx.ALIGN_CENTRE, margins: Tuple[int, int, int, int] = (2,2,2,2,)):
        if panel_number >= self.GetFieldsCount() and panel_number >= 0:
            self.SetFieldsCount(panel_number + 1)
        if panel_number not in self._static_bitmaps.keys():
            self._static_bitmaps[panel_number] = None
            self._bitmap_names[panel_number] = None


        rect: wx.Rect = self.GetFieldRect(panel_number)
        if panel_number in self._static_bitmaps.keys():
            if bitmap_name is None:
                if self._static_bitmaps[panel_number] is not None:
                    self._static_bitmaps[panel_number].Unbind(wx.EVT_LEFT_DOWN)
                    self._static_bitmaps[panel_number].Destroy()
                    self._static_bitmaps[panel_number] = None
                    self.Refresh()
                self._bitmap_names[panel_number] = None


        if bitmap_name is not None and bitmap_name != self._bitmap_names[panel_number]:

            bitmap: wx.Bitmap = self._image_list.get(bitmap_name,wx.Bitmap)
            if bitmap:
                x_offset = margins[0]
                y_offset = margins[2]
                if align & wx.ALIGN_CENTER_HORIZONTAL == wx.ALIGN_CENTER_HORIZONTAL:
                    x_offset = math.ceil((rect.GetWidth() - bitmap.GetWidth()) / 2) + margins[0] - margins[1]
                if align & wx.ALIGN_CENTER_VERTICAL == wx.ALIGN_CENTER_VERTICAL:
                    y_offset = math.ceil((rect.GetHeight() - bitmap.GetHeight()) / 2) + margins[2] - margins[3]
                if align & wx.ALIGN_RIGHT == wx.ALIGN_RIGHT:
                    x_offset = rect.GetX() - bitmap.GetWidth() - margins[1]
                if align & wx.ALIGN_BOTTOM == wx.ALIGN_BOTTOM:
                    y_offset = rect.GetY() - bitmap.GetHeight() - margins[3]

                bmp_btn = wx.StaticBitmap(self, -1, bitmap, (rect.GetX() + x_offset, rect.GetY()+y_offset), name=f'bitmap_{panel_number}')
                bmp_btn.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_click)
                #bmp_btn = wx.StaticBitmap(self, -1, bitmap, (x, y), (x_end, y_end))
                self._static_bitmaps[panel_number] = bmp_btn
                self._bitmap_names[panel_number] = bitmap_name
                self.Refresh()
            else:
                mlogger.error(f'{self} не найдена иконка {bitmap_name}')
            # bmpbtn.Bind(wx.EVT_LEFT_DOWN, self.OnStatusClick)


        #self.reposition()
        #if __debug__:
        #    mlogger.debug('BasicStatusBar для панели {0} установка изображения: {1}'.format(panel_number, bitmap))

    def is_panel_bitmap_set(self, panel_number: int):
        if 0 <= panel_number < self.GetFieldsCount():
            if self._static_bitmaps[panel_number] is not None:
                return True
        return False


    #def get_panel_bitmap(self, panel_number:int):
    #    if 0<= panel_number < self.GetFieldsCount() and panel_number in self._static_bitmaps.keys():
    #        return self._bitmaps[panel_number]
    #    return None

    def set_panel_width(self, width: int, panel_number: int):
        if self.GetFieldsCount() <= panel_number >= 0:
            self.SetFieldsCount(panel_number + 1)
        widths = []
        for i in range(self.GetFieldsCount()):
            if i==panel_number:
                widths.append(width)
            else:
                widths.append(self.GetStatusWidth(i))
        self.SetStatusWidths(widths)
        #self.reposition()
        #if __debug__:
        #    mlogger.debug('BasicStatusBar для панели {0} установка ширины: {1}'.format(panel_number, width))

    def fit_panel(self, panel_number: int):
        if self.GetFieldsCount() >= panel_number >= 0:
            data_str = self.GetStatusText(panel_number)
            width = self.GetTextExtent(data_str)[0]
            self.set_panel_width(width, panel_number)

    #def on_size(self, evt: wx.SizeEvent):
    #    evt.Skip()
    #    self.reposition()  # for normal size events
    #    # Set a flag so the idle time handler will also do the repositioning.
    #    # It is done this way to get around a buglet where GetFieldRect is not
    #    # accurate during the EVT_SIZE resulting from a frame maximize.
    #    self.size_changed = True

    #def on_idle(self, evt: wx.IdleEvent):
    #    evt.Skip()
    #    if self.size_changed:
    #        self.reposition()

    # reposition the checkbox
    #def reposition(self):
    #    #rect = self.GetFieldRect(1)
    #    #rect.x += 1
    #    #rect.y += 1
    #    # self.bmpbtn.SetRect(rect)
    #    self.size_changed = False

    #def OnStatusClick(self, event):
    #    self.SetImage(random.randrange(0, 5))
    #    self.SetText(str(random.randrange(0, 65535)))

class BasicToolBar(wx.ToolBar):
    _tools_list: Dict[int, wx.ToolBarToolBase]
    _commands: Dict[int, WxCommand]
    _parent: Any
    def __init__(self, parent: Union[wx.Control, wx.Panel, wx.Frame, wx.BoxSizer, wx.GridSizer, 'BasicWindow', 'BasicDialog'], style= wx.TB_FLAT):
        self._parent = parent
        wx.ToolBar.__init__(self, parent, wx.ID_ANY, pos=wx.DefaultPosition, size=wx.DefaultSize, style=style, name="")
        self._commands: Dict[int, WxCommand] = {}
        self._tools_list: Dict[int, wx.ToolBarToolBase] = {}
        if type(parent).__class__.__name__ == wx.Frame.__name__:
            parent.SetToolBar(self)
        elif type(parent).__class__.__name__ == wx.BoxSizer.__name__ or type(parent).__class__.__name__ == wx.GridSizer.__name__:
            parent.Add(self, 0, wx.EXPAND | wx.ALL, 0)

    def set_size(self, size: wx.Size):
        self.SetToolBitmapSize(wx.Size(size.GetWidth(), size.GetHeight()))

    def add_tool_item(self, cmd: WxCommand):
        if cmd.iid not in self._tools_list.keys():
            tool = self.AddTool(cmd.iid, cmd.name, cmd.Bitmap, shortHelp=cmd.name, kind=wx.ITEM_NORMAL)
            self.Bind(wx.EVT_TOOL, cmd.execute, id=cmd.iid)
            # self.AddSimpleTool(wx.ID_ANY, cmd.Bitmap)
            self._tools_list[cmd.iid] = tool
            self._commands[cmd.iid] = cmd
            self.Realize()
            if __debug__:
                mlogger.debug(f'{self}  добавление элемента: {cmd.name}')
        else:
            mlogger.error(f"{self}  Недопустимо добавлять в toolbar элементы с одинаковым Id")

    def add_tool_ctrl(self, control, title):
        # self.AddStretchableSpace()
        self.AddControl(control, title)
        # self.AddStretchableSpace()
        self.Realize()
        # self.AddControl(control)
        if __debug__:
            mlogger.debug(f'{self} добавление элемента: {control} с именем {title}')

    def update_tool_state(self, cmd: WxCommand, state: bool):
        if cmd.iid in self._tools_list.keys():
            self.EnableTool(cmd.iid, state)

    def update_wxcommand_states(self):
        cmd: WxCommand
        for cmd in self._commands.values():
            if cmd.iid in self._tools_list.keys():
                self.update_tool_state(cmd, cmd.can_execute())
        if __debug__:
            mlogger.debug(f'{self} обновление статусов')

    def add_separator_item(self):
        self.AddSeparator()
        if __debug__:
            mlogger.debug(f'{self} добавление разделителя')

    def add_tool_check(self, cmd: WxCommand):
        if cmd.iid not in self._tools_list.keys():
            tool = self.AddTool(cmd.iid, cmd.name, cmd.Bitmap, shortHelp=cmd.name, kind=wx.ITEM_CHECK)
            self.Bind(wx.EVT_TOOL, self.on_tool, id=cmd.iid)  # , cmd.Execute, id=cmd.Id)
            # self.AddSimpleTool(wx.ID_ANY, cmd.Bitmap)
            self._tools_list[cmd.iid] = tool
            self._commands[cmd.iid] = cmd
            self.Realize()
            if __debug__:
                mlogger.debug(f'{self}  добавление элемента: {cmd.name}')
        else:
            mlogger.error(f"{self}  недопустимо добавлять в toolbar элементы с одинаковым Id")

    def on_tool(self, event: wx.CommandEvent):
        if self == event.GetEventObject():
            if event.GetId() in self._commands.keys():
                cmd: WxCommand = self._commands[event.GetId()]
                cmd.execute(event)

    def get_tool_state_by_cmd(self, cmd: WxCommand):
        if cmd.iid in self._tools_list.keys():
            return self.GetToolState(cmd.iid)
        return None

    def get_tool_state_by_iid(self, iid: int):
        if iid in self._tools_list.keys():
            return self.GetToolState(iid)
        return None


class BasicSideNotebook(wx.lib.agw.labelbook.LabelBook):
    _local_pages: Dict[str, Union[wx.Frame, wx.Panel]] = {}
    _local_pages_nums: Dict[str, int] = {}
    _rescale_size: wx.Size
    _registered_on_changed: List[Callable[[str, str, ], None]] = []
    _image_list: ImageList
    _parent: Any
    def __init__(self, parent: Union[wx.Frame, wx.Panel, wx.Dialog], image_size_list: wx.Size):
        self._parent = parent
        ast = wx.lib.agw.labelbook.INB_FIT_BUTTON | wx.lib.agw.labelbook.INB_FIT_LABELTEXT | wx.lib.agw.labelbook.INB_LEFT
        ast |= wx.lib.agw.labelbook.INB_USE_PIN_BUTTON
        wx.lib.agw.labelbook.LabelBook.__init__(self, parent, agwStyle=ast)
        self._local_pages = {}
        self._local_pages_nums = {}
        self._rescale_size = image_size_list
        self._registered_on_changed = []
        self._rescale_size = image_size_list
        self._image_list = ImageList(wx.Size(image_size_list.GetWidth(), image_size_list.GetHeight()))
        self._set_image_list(self._image_list)
        self.Bind(wx.lib.agw.labelbook.EVT_IMAGENOTEBOOK_PAGE_CHANGED, self._on_page_changed)
        self.Bind(wx.lib.agw.labelbook.EVT_IMAGENOTEBOOK_PAGE_CHANGING, self._on_page_changing)

    def add_image(self, name: str, img: Union[wx.Image, wx.Bitmap, str]):
        self._image_list.add(name, img)

    def set_colour(self, index: int, color: wx.Colour):
        color_ids = [wx.lib.agw.labelbook.INB_TAB_AREA_BACKGROUND_COLOUR,
                     wx.lib.agw.labelbook.INB_ACTIVE_TAB_COLOUR,
                     wx.lib.agw.labelbook.INB_TABS_BORDER_COLOUR,
                     wx.lib.agw.labelbook.INB_TEXT_COLOUR,
                     wx.lib.agw.labelbook.INB_ACTIVE_TEXT_COLOUR,
                     wx.lib.agw.labelbook.INB_HILITE_TAB_COLOUR]
        if 0<=index<len(color_ids):
            self.SetColour(color_ids[index], color)
        else:
            if __debug__:
                mlogger.error(f'{self} Ошибка установки цвета')

    def _set_image_list(self, image_list: ImageList):
        self._image_list = image_list
        self.AssignImageList(self._image_list.image_list)

    def set_page_image(self, page_name: str, image_name: Optional[str]):
        if page_name not in self._local_pages.keys():
            mlogger.warning(f"{self} Страница с именем \"{page_name}\" не найдена (set page image)")
            return
        page_num = 0
        for cur_page_name, page_num_i in self._local_pages_nums.items():
            if page_name == cur_page_name:
                page_num = page_num_i
        if image_name is None:
            # noinspection PyArgumentList
            self.SetPageImage(page_num,-1)
        else:
            image_index = self._image_list.get_index(image_name)

            if image_index is not None:
                # noinspection PyArgumentList
                self.SetPageImage(page_num, image_index)

    def clear(self):
        # ВНИМАНИЕ! Если удалять страницу через delete_page, то будет вызвано событие EVT_NOTEBOOK_PAGE_CHANGED
        # что может привести к странным последствиям в виде выбора другой страницы, которая уже была удалена вроде ???
        # короче очередной глюк wxWidgets
        self._local_pages.clear()
        self._local_pages_nums.clear()
        self.DeleteAllPages()

    def delete_page(self, page_name: str):
        found_del_page = False
        del_index = -1
        for cur_page_name, cur_index in self._local_pages_nums.items():
            if cur_page_name == page_name:
                del_index = cur_index
                found_del_page = True
            if found_del_page:
                self._local_pages_nums[cur_page_name] -= 1
        if found_del_page:
            del self._local_pages_nums[page_name]
            del self._local_pages[page_name]
            # непосредственное удаление страницы должно происходить в конце,
            # так как DeletePage вызывает on_page_changed, и все связанные с этим события могут привести к неверному поиску страницы
            self.DeletePage(del_index)

        else:
            mlogger.error(f"{self} Страница \"{page_name}\" не найдена")

    def add_page(self, page_name: str, panel: Union[wx.Panel, wx.lib.scrolledpanel.ScrolledPanel]):
        if page_name in self._local_pages.keys():
            mlogger.warning(f"{self} Страница с именем \"{page_name}\" уже существует ")
            return

        #if image is None:
        self.AddPage(panel, page_name)
        #self._image_list.Add(wx.Bitmap(self._rescale_size.width, self._rescale_size.height))
        if __debug__:
            mlogger.debug(f"{self} Страница \"{page_name}\" добавлена без картинки")
        #else:
        #    self._image_list.Add(rescale_image_to_bitmap(image, custom_size=self._rescale_size))
        #    if __debug__:
        #        mlogger.debug("Страница \"{0}\" добавлена с картинкой".format(page_name))
        #    cur_image_id = self.GetPageCount()
        #    self.AddPage(panel, page_name, imageId=cur_image_id)
        self._local_pages[page_name] = panel
        self._local_pages_nums[page_name] = self.GetPageCount() - 1

    def select_page(self, page_name: str):
        if page_name not in self._local_pages.keys():
            mlogger.warning(f"{self} Страница с именем \"{page_name}\" не найдена (select page)")
            return
        for cur_page_name, page_num in self._local_pages_nums.items():
            if page_name == cur_page_name:
                # noinspection PyArgumentList
                self.SetSelection(page_num)
                #cmd_evt = wx.BookCtrlEvent(wx.wxEVT_NOTEBOOK_PAGE_CHANGED, self.GetId())
                #cmd_evt.SetEventObject(self)
                #cmd_evt.SetOldSelection(-1)
                #cmd_evt.SetSelection(page_num)
                #wx.PostEvent(self, cmd_evt)

    def have_page(self, page_name: str):
        return page_name in self._local_pages.keys()

    def _on_page_changed(self, event: wx.BookCtrlEvent):
        if self == event.GetEventObject():
            old = event.GetOldSelection()
            new = event.GetSelection()
            #sel = self.GetSelection()
            old_name = ""
            new_name = ""
            for page_name, page in self._local_pages_nums.items():
                if old == page:
                    old_name = page_name
                if new == page:
                    new_name = page_name
            if __debug__:
                mlogger.debug(f"{self} Окончание перехода со страницы \"{old_name}\" на страницу \"{new_name}\"")
            for func in self._registered_on_changed:
                func(old_name, new_name)
        event.Skip()

    def _on_page_changing(self, event: wx.BookCtrlEvent):
        if self == event.GetEventObject():
            sel = self.GetSelection()
            sel_name = ""
            for page_name, page in self._local_pages_nums.items():
                if sel == page:
                    sel_name = page_name
            if __debug__:
                mlogger.debug(f"{self} Начало перехода со страницы \"{sel_name}\"")
        event.Skip()



    def register_on_changed(self, func: Callable[[str, str,],None]):
        self._registered_on_changed.append(func)

    def unregister_on_changed(self, func: Callable[[str, str,],None]):
        if func in self._registered_on_changed:
            self._registered_on_changed.remove(func)

    def get_selected_page_name(self) -> str:
        cur_page = self.GetSelection()
        for page_name, page in self._local_pages_nums.items():
            if cur_page == page:
                return page_name

    def get_selected_page(self):
        cur_page = self.GetSelection()
        for page_name, page in self._local_pages_nums.items():
            if cur_page == page:
                if page_name in self._local_pages.keys():
                    return self._local_pages[page_name]
        return None

    def get_page_instances(self):
        return list(self._local_pages.values())

    def get_page_names(self):
        return list(self._local_pages.keys())

    def get_page(self, name: Optional[str]):
        if name in self._local_pages.keys():
            return self._local_pages[name]
        return None

    def get_control_page_name(self, control: Any)->Optional[str]:
        for name, c in self._local_pages.items():
            if c == control:
                return name
        return None


class BasicDropFileTarget(wx.FileDropTarget):
    _allowed_multiple: bool
    _accept_files: bool
    window: Union['BasicFileSelect', 'BasicTree']
    def __init__(self, window: Union['BasicFileSelect', 'BasicTree', wx.grid.Grid], allowed_multiple: bool):
        wx.FileDropTarget.__init__(self)
        self.window = window
        self._allowed_multiple = allowed_multiple
        self._accept_files = True
        #self.hide_drag_image()


    #def hide_drag_image(self):
    #    try:
    #        import ctypes.wintypes
    #        ctypes.wintypes.s
    #        ctypes.windll.shell32.DragAcceptFiles(self.window.GetHandle(), True)
    #        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("myapp")
    #    except Exception as ex:
    #        print(f'some error {ex}')

    @property
    def accept_files(self):
        return self._accept_files

    @accept_files.setter
    def accept_files(self, val: bool):
        if type(val) == bool:
            self._accept_files  =val

    def OnDragOver(self, x, y, _def_result):
        #return wx.DragError  # вызывает ошибку - возвращать нельзя
        #return wx.DragCancel  # вызывает ошибку это какая-то внутренняя фигня - возвращать нельзя
        #return wx.DragNone  # показывает, что файл перенести нелья и OnDropFiles Не вызывается
        #return wx.DragCopy  # показывает плюс и картинку копирования
        #return wx.DragMove # показывает картинку перемещния и говорит перемещение
        if not self.accept_files:
            return wx.DragNone
        do: wx.DataObject = self.GetDataObject()
        frmt: wx.DataFormat
        cur_frmt = None
        for frmt in do.GetAllFormats():
            if not cur_frmt:
                cur_frmt = frmt
            #wx.DF_INVALID
            #wx.DF_TEXT
            #wx.DF_BITMAP
            #wx.DF_METAFILE
            # wx.DF_UNICODETEXT
            # wx.DF_FILENAME
            # wx.DF_HTML
            # wx.DF_PNG
            if frmt.GetType() != wx.DF_FILENAME:
                return wx.DragNone
        #buf = io.BytesIO()
        #do.GetDataHere(cur_frmt, buf)
        # получить количество файлов невозможно
        return wx.DragLink


        #elif not self._allowed_multiple and data_size == 1:
        #    return wx.DragLink
        #return wx.DragNone

    def OnEnter(self, x, y, def_result):
        return def_result

    def OnLeave(self):
        pass


    def execute_drop_files(self, filenames):
        if len(filenames) == 1:
            if issubclass(type(self.window), BasicFileSelect):
                set_file = True
                if self.window.get_value():
                    if self.window.get_value() != filenames[0]:
                        set_file = self.window.can_replace_file_dialog_result()
                if set_file:
                    self.window.set_value(filenames[0])
            else:
                message_box(self.window, 'Предупреждение', 'Невозможно добавить несколько файлов. Перетащите только один.', wx.ICON_WARNING)
        else:
            message_box(self.window, 'Предупреждение', 'Невозможно добавить несколько файлов. Перетащите только один.', wx.ICON_WARNING)

    def OnDropFiles(self, x, y, filenames):
        if type(self.window) == BasicFileSelect:
            wx.CallAfter(self.execute_drop_files, filenames)
        return True

___hittest_names = {   'ABOVE': 1,
                    'BELOW': 2,
                    'NOWHERE':4,
                    'TONITEM':80,
                    'ONITEMBUTTON' : 8,
                    'ONITEMICON' : 16,
                    'ONITEMINDENT' : 32,
                    'ONITEMLABEL' : 64,
                    'ONITEMLOWERPART' : 4096,
                    'ONITEMRIGHT' : 128,
                    'ONITEMSTATEICON' : 256,
                    'ONITEMUPPERPART' : 2048,
                    'TOLEFT' : 512,
                    'TORIGHT' : 1024}



class BasicTree(wx.TreeCtrl, EventPublisher, WxEvents):
    class TreeItemInfo:
        background_color: Optional[wx.Colour]
        is_bold: Optional[bool]
        drop_highlight: Optional[bool]
        font: Optional[wx.Font]
        image: Optional[str]
        text_color: Optional[wx.Colour]
        image_selected: Optional[str]
        image_expanded: Optional[str]
        image_selected_expanded: Optional[str]

        def __init__(self):
            self.background_color = None
            self.is_bold = None
            self.drop_highlight = None
            self.font = None
            self.image = None
            self.text_color = None
            self.image_selected = None
            self.image_expanded = None
            self.image_selected_expanded = None

    class BasicTreeDropTarget(wx.DropTarget):
        _tree_ctrl: 'BasicTree'
        _internal_drag_objects: List[Any]
        _external_drag_object: Any
        _mark_color: wx.Colour
        _last_scroll_time: datetime.datetime

        _textdo: wx.TextDataObject  # DF_TEXT , DF_UNICODETEXT
        _imagedo: wx.ImageDataObject  # DF_PNG
        _htmldo: wx.HTMLDataObject  # DF_HTML
        _filedo: wx.FileDataObject  # DF_FILENAME
        _bmpdo : wx.BitmapDataObject  # DF_BITMAP
        internal_as_external: bool

        def __init__(self, treectrl: 'BasicTree', internal_as_external):
            wx.DropTarget.__init__(self)
            self._last_scroll_time = datetime.datetime.now()
            #WxEvents.__init__(self)
            self._tree_ctrl = treectrl
            self._internal_drag_objects = []
            self._external_drag_object = None
            self._mark_color = wx.ColourDatabase().FindName("YELLOW")
            # wx.DF_INVALID
            # wx.DF_TEXT
            # wx.DF_BITMAP
            #wx.DF_METAFILE
            #wx.DF_UNICODETEXT
            #wx.DF_FILENAME
            #wx.DF_HTML
            #wx.DF_PNG
            self._do = wx.DataObjectComposite()
            self._textdo = wx.TextDataObject() # DF_TEXT , DF_UNICODETEXT
            self._imagedo = wx.ImageDataObject() # DF_PNG
            self._htmldo = wx.HTMLDataObject() # DF_HTML
            self._filedo = wx.FileDataObject() # DF_FILENAME
            self._bmpdo = wx.BitmapDataObject() # DF_BITMAP

            #self._do.Add(self._urldo)
            self._do.Add(self._textdo)
            self._do.Add(self._imagedo)
            self._do.Add(self._htmldo)
            self._do.Add(self._filedo)
            self._do.Add(self._bmpdo)

            self.SetDataObject(self._do)
            self.internal_as_external = internal_as_external

        def OnData(self, x, y, def_result):
            """при получении данных после отпускания мыши, def_result = то действие которое просит выполнить пользователь"""
            items_to_process = self._internal_drag_objects
            # noinspection PyArgumentList
            tree_item_id, flags = self._tree_ctrl.HitTest(wx.Point(x, y))
            recv_item = None
            if tree_item_id and flags & (wx.TREE_HITTEST_ONITEMLABEL | wx.TREE_HITTEST_ONITEMICON):
                recv_item = self._tree_ctrl.GetItemData(tree_item_id)

            if not self._internal_drag_objects:
                if self._tree_ctrl.do_convert_external_data_to_items:
                    new_items = []
                    result, message =self._tree_ctrl.do_convert_external_data_to_items(self._external_drag_object, new_items)
                    if result is False:
                        if not message:
                            wx.CallAfter(message_box, self._tree_ctrl, 'Ошибка', 'Полученные данные не получилось преобразовать', wx.ICON_ERROR)
                            #message_box(self._tree_ctrl, 'Ошибка', 'Полученные данные не получилось преобразовать', wx.ICON_ERROR)
                        else:
                            wx.CallAfter(message_box, self._tree_ctrl, 'Ошибка', message, wx.ICON_ERROR)
                            #message_box(self._tree_ctrl, 'Ошибка', message, wx.ICON_ERROR)
                        def_result = wx.DragNone
                    elif result is True:
                        items_to_process = new_items
            if self.internal_as_external:
                items_to_process = self._external_drag_object

            if self._tree_ctrl.do_recieve_internal_data:
                result, message = self._tree_ctrl.do_recieve_internal_data(recv_item, items_to_process, def_result)
                if result is False:
                    if not message:
                        wx.CallAfter(message_box, self._tree_ctrl,'Ошибка', 'Полученные данные не получилось обработать', wx.ICON_ERROR)
                        #message_box(self._tree_ctrl,'Ошибка', 'Полученные данные не получилось обработать', wx.ICON_ERROR)
                    else:
                        wx.CallAfter(message_box, self._tree_ctrl, 'Ошибка', message, wx.ICON_ERROR)
                        #message_box(self._tree_ctrl, 'Ошибка', message, wx.ICON_ERROR)
                    def_result = wx.DragNone

            self.drop_complete_external()
            self._internal_drag_objects.clear()
            self._external_drag_object = None
            return def_result


        def OnDrop(self, x, y):  # real signature unknown; restored from __doc__
            """при отпускании мыши с данными вызывается один раз"""
            recv_raw_data = None
            recv_item = None
            # noinspection PyArgumentList
            tree_item_id, flags = self._tree_ctrl.HitTest(wx.Point(x, y))
            if tree_item_id and flags & (wx.TREE_HITTEST_ONITEMLABEL | wx.TREE_HITTEST_ONITEMICON):
                recv_item = self._tree_ctrl.GetItemData(tree_item_id)
                self._tree_ctrl._last_item_id = tree_item_id
            if recv_item is None:
                return False

            if self.GetData():
                rf:wx.DataFormat = self._do.GetReceivedFormat()
                rf_type = rf.GetType()
                if rf_type in [wx.DF_TEXT, wx.DF_UNICODETEXT]:
                    if self._textdo.GetDataSize() > 0:
                        recv_raw_data = self._textdo.GetText()
                elif rf_type == wx.DF_HTML:
                    if self._htmldo.GetDataSize() > 0:
                        recv_raw_data = self._textdo.GetText()
                elif rf_type == wx.DF_BITMAP:
                    if self._bmpdo.GetDataSize() > 0:
                        recv_raw_data = self._bmpdo.GetBitmap()
                elif rf_type == wx.DF_FILENAME:
                    if self._filedo.GetDataSize() > 0:
                        recv_raw_data = self._filedo.GetFilenames()
                elif rf_type == wx.DF_TIFF:
                    if self._imagedo.GetDataSize() > 0:
                        recv_raw_data = self._imagedo.GetImage()

            drag_complete_result = False
            if self._tree_ctrl.can_drop_items:
                if self._internal_drag_objects and not self.internal_as_external:
                    if self._tree_ctrl.can_drop_items(self._internal_drag_objects):
                        drag_complete_result = True
                else:
                    self._external_drag_object = recv_raw_data
                    if self._tree_ctrl.can_drop_items(recv_raw_data):
                        drag_complete_result = True

            if not drag_complete_result:
                self.drop_complete_external()
                self._internal_drag_objects.clear()
                self._external_drag_object = None
            return drag_complete_result

        def OnDragOver(self, x, y, def_result):
            """при попадании мыши на окно с перетаскиваемыми данными постоянно по координатам"""
            # return wx.DragError  # вызывает ошибку - возвращать нельзя
            # return wx.DragCancel  # вызывает ошибку это какая-то внутренняя фигня - возвращать нельзя
            # return wx.DragNone  1# показывает, что файл перенести нелья и OnDropFiles Не вызывается
            # return wx.DragCopy  2# показывает плюс и картинку копирования
            # return wx.DragMove 3 # показывает картинку перемещния и говорит перемещение
            # return wx.DragLink 4 # показывает картинку перемещния и говорит перемещение
            # noinspection PyArgumentList
            obj, flags = self._tree_ctrl.HitTest(wx.Point(x,y))
            drag_result = def_result
            if obj and flags & (wx.TREE_HITTEST_ONITEMLABEL | wx.TREE_HITTEST_ONITEMICON | wx.TREE_HITTEST_ONITEM | wx.TREE_HITTEST_ONITEMBUTTON | wx.TREE_HITTEST_ONITEMRIGHT | wx.TREE_HITTEST_ONITEMINDENT):
                if flags & (wx.TREE_HITTEST_ONITEMLABEL | wx.TREE_HITTEST_ONITEMICON):
                    if not self._tree_ctrl.IsSelected(obj):
                        self._tree_ctrl.UnselectAll()
                        self._tree_ctrl.SelectItem(obj, True)
                else:
                    drag_result = wx.DragNone
                if flags & (wx.TREE_HITTEST_ONITEMLABEL | wx.TREE_HITTEST_ONITEMICON | wx.TREE_HITTEST_ONITEMBUTTON):
                    if not self._tree_ctrl.IsExpanded(obj):
                        self._tree_ctrl.Expand(obj)
                self._scroll_tree_list(x, y)
            return drag_result

        def OnEnter(self, x, y, def_result):  # real signature unknown; restored from __doc__
            """при заведении объекта в окно вызывается один раз"""

            self._tree_ctrl.SetFocus()
            if self._internal_drag_objects:
                for item in self._internal_drag_objects:
                    tree_item_id = self._tree_ctrl.get_tree_item_id(item)
                    if tree_item_id is not None:
                        self._tree_ctrl.SetItemBackgroundColour(tree_item_id, self._mark_color)
            drag_result = def_result
            return drag_result
        
        def OnLeave(self):  # real signature unknown; restored from __doc__
            self._tree_ctrl.GetParent().SetFocus()
        
        def _scroll_tree_list(self, _x:int, y:int):
            if (datetime.datetime.now()-self._last_scroll_time).microseconds/1000>100:
                tree_ctrl_size: wx.Size = self._tree_ctrl.GetSize()
                if y < tree_ctrl_size.GetHeight()/6:
                    self._tree_ctrl.ScrollLines(-1)
                if y > tree_ctrl_size.GetHeight()*5/6:
                    self._tree_ctrl.ScrollLines(1)
                self._last_scroll_time = datetime.datetime.now()
                
        def set_drag_items(self, items: List[Any]):
            self._internal_drag_objects = items

        def get_drag_items(self):
            return self._internal_drag_objects

        def drop_complete_external(self):
            for item in self._internal_drag_objects:
                tree_item_id = self._tree_ctrl.get_tree_item_id(item)
                if tree_item_id is not None:
                    self._tree_ctrl.SetItemBackgroundColour(tree_item_id, None)


        def send_data(self, data_list: List[Any], copy_only: bool)->bool:
            for item in self._internal_drag_objects:
                tree_item_id = self._tree_ctrl.get_tree_item_id(item)
                if tree_item_id is not None:
                    self._tree_ctrl.SetItemBackgroundColour(tree_item_id, self._mark_color)
            src: wx.DropSource = wx.DropSource(self._tree_ctrl)

            tobj = wx.DataObjectComposite()
            used_types = []
            for item in data_list:
                if type(item) not in used_types:
                    used_types.append(type(item))
                else:
                    mlogger.error(f'{self} невозможно добавить элемент типа {type(item)}, такой тип уже добавлен')
                    continue
                if type(item) == str:
                    textobj = wx.TextDataObject()
                    textobj.SetText(item)
                    tobj.Add(textobj)
                elif type(item) == list:
                    fileobj = wx.FileDataObject()
                    for sitem in item:
                        fileobj.AddFile(sitem)
                    tobj.Add(fileobj)
                elif type(item) == wx.Bitmap:
                    bitmapobj = wx.BitmapDataObject()
                    tobj.Add(bitmapobj)

            src.SetData(tobj)
            default_action = wx.Drag_AllowMove
            if copy_only:
                default_action = wx.Drag_CopyOnly
            result = src.DoDragDrop(default_action)
            self.drop_complete_external()
            self._internal_drag_objects.clear()
            self._external_drag_object = None
            if result in [wx.DragCopy, wx.DragMove, wx.DragLink]:
                return True
            return False


    _root_item: wx.TreeItemId

    _multiple_selection: bool
    _should_sort: bool
    _drop_file_target: BasicTreeDropTarget
    _drag_only_copy: bool


    _items: Dict[Any, wx.TreeItemId]
    _image_list: ImageList
    _sort_items: List[wx.TreeItemId]


    can_drag_items: Optional[Callable[[Any], bool]]
    can_drop_items: Optional[Callable[[Any], bool]]
    do_convert_item_to_external_data: Optional[Callable[[List[Any], List[Any]], Tuple[bool, str]]]
    do_convert_external_data_to_items: Optional[Callable[[List[Any], List[Any]], Tuple[bool, str]]]
    do_recieve_internal_data: Optional[Callable[[Any, List[Any], int], Tuple[bool, str]]]
    compare_items: Optional[Callable[[Any, Any], Optional[bool]]]
    on_item_dclick: Optional[Callable[[Any], None]]

    _last_item_id: Optional[wx.TreeItemId]

    on_selection_changed: Optional[Callable[[List[Any]], None]]

    def __init__(self, parent: BasicPanel, select_multiple: bool, edit_labels: bool, should_sort: bool, internal_as_external: bool):
        default_style = wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT

        if select_multiple:
            default_style |= wx.TR_MULTIPLE

        if edit_labels:
            default_style |= wx.TR_EDIT_LABELS

        wx.TreeCtrl.__init__(self, parent, style=default_style)
        EventPublisher.__init__(self)
        WxEvents.__init__(self)
        self._drag_only_copy = True
        self._multiple_selection = select_multiple
        self._should_sort = should_sort

        self._drop_file_target = self.BasicTreeDropTarget(self, internal_as_external)
        self.SetDropTarget(self._drop_file_target)

        self._image_list = ImageList(GuiWidgetSettings.treectrl_bitmap_size)
        self.AssignImageList(self._image_list.image_list)

        self.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_tree_selected)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_tree_item_activated)
        self.Bind(wx.EVT_TREE_DELETE_ITEM, self._on_tree_item_deleted)

        if edit_labels:
            self.Bind(wx.EVT_TREE_BEGIN_LABEL_EDIT, self._on_tree_item_begin_edit)
            self.Bind(wx.EVT_TREE_END_LABEL_EDIT, self._on_tree_item_end_edit)

        self.Bind(wx.EVT_TREE_BEGIN_DRAG, self._on_tree_begin_drag)
        self.Bind(wx.EVT_TREE_BEGIN_RDRAG, self._on_tree_begin_right_drag)
        self.Bind(wx.EVT_TREE_END_DRAG, self._on_tree_end_drag)
        self.Bind(wx.EVT_CHAR, self._on_tree_key_pressed)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        self._root_item = self.AddRoot('root')
        self._items = {}
        self.can_drag_items = None
        self.can_drop_items = None
        self.do_convert_item_to_external_data = None
        self.do_convert_external_data_to_items = None
        self.do_recieve_internal_data = None
        self.compare_items = None
        self.on_selection_changed = None
        self._sort_items = []
        self._last_item_id = None



    @property
    def drag_only_copy(self):
        return self._drag_only_copy

    @drag_only_copy.setter
    def drag_only_copy(self, val: bool):
        if type(val) == bool:
            self._drag_only_copy = val

    def OnCompareItems(self, tree_item1: wx.TreeItemId, tree_item2: wx.TreeItemId):
        if self._should_sort:
            compare_result = None
            if self.compare_items:
                item1 = self.GetItemData(tree_item1)
                item2 = self.GetItemData(tree_item2)
                compare_result = self.compare_items(item1, item2)

            if compare_result is None:
                item_text1 = self.GetItemText(tree_item1).lower().strip()
                item_text2 = self.GetItemText(tree_item2).lower().strip()
                if item_text1 < item_text2:
                    return -1
                elif item_text1 == item_text2:
                    return 0
                else:
                    return 1
            else:
                return compare_result
        else:
            return 0

    @WxEvents.debounce(0.35, False)
    def _update_sort(self):
        frozen = self.IsFrozen()
        if not frozen:
            self.Freeze()
        #items = self.get_selected_items()

        for tree_item_id in self._sort_items:
            self.SortChildren(tree_item_id)
        if self._last_item_id is not None:
            if self._last_item_id.IsOk():
                self.EnsureVisible(self._last_item_id)
        if not frozen:
            self.Thaw()


    def _sort(self, tree_item_id: wx.TreeItemId):
        if self._should_sort:
            if tree_item_id.IsOk():
                tree_item_parent = self.GetItemParent(tree_item_id)
                if tree_item_parent not in self._sort_items:
                    self._sort_items.append(tree_item_parent)
                #if ensure_visible_item_id is not None:
                # noinspection PyArgumentList
            self._update_sort()

    def _on_tree_key_pressed(self, evt: wx.KeyEvent):
        key_code = evt.GetKeyCode()
        if key_code == wx.WXK_ESCAPE:
            self.UnselectAll()
            if not self._multiple_selection:
                if self.on_selection_changed:
                    self.on_selection_changed([])
        evt.Skip()

    def _on_tree_begin_drag(self, evt: wx.TreeEvent):
        internal_drag_objects = []
        if self._multiple_selection:
            dragging_tree_item_ids = self.GetSelections()
            for tree_item_id in dragging_tree_item_ids:
                internal_drag_objects.append(self.GetItemData(tree_item_id))
        else:
            dragging_tree_item_id = self.GetSelection()
            internal_drag_objects.append(self.GetItemData(dragging_tree_item_id))

        if self.can_drag_items and self.can_drag_items(internal_drag_objects):
            self._drop_file_target.set_drag_items(internal_drag_objects)
            data_list = []
            result = False
            message = ''
            if self.do_convert_item_to_external_data:
                result, message = self.do_convert_item_to_external_data(internal_drag_objects, data_list)
            if result is True:
                if not self._drop_file_target.send_data(data_list, self._drag_only_copy):
                    message_box(self, 'Предупреждение', 'Операция отменена', wx.ICON_WARNING)
            elif result is False:
                if message:
                    message_box(self, 'Ошибка', message, wx.ICON_WARNING)
                else:
                    message_box(self, 'Ошибка', 'Невозможно преобразовать данные для отправки', wx.ICON_WARNING)
            #self._drop_file_target.send_data()
            #src = wx.DropSource(self)
            #tobj = wx.DataObjectComposite()
            #textobj = wx.TextDataObject()
            #tobj.Add(textobj)
            ##tobj = wx.FileDataObject()
            #src.SetData(tobj)
            #result = src.DoDragDrop(wx.Drag_AllowMove)
            #self._drop_file_target.drop_complete_external()
            #if result in [wx.DragMove, wx.DragCopy]:
            #    if self.do_convert_item_to_external_data:
            #        data_list = []
            #        if not self.do_convert_item_to_external_data(internal_drag_objects, data_list):
            #            message_box(self, 'Ошибка', 'Невозможно выполнить операцию', wx.ICON_WARNING)
            #        print('логика преобразования внутренних данных в объект для отправки')
            #        for item in data_list: # запишем преобразованные данные в
            #            pass
            #else:
            #    message_box(self, 'Ошибка', 'Операция отклонена получателем', wx.ICON_WARNING)
        #evt.Allow() - нужно разрешить если операция выполняется внутри приложения, но тогда не могут выполнится операции по изменению выбранных объектов
        evt.Skip()

    def _on_tree_begin_right_drag(self, evt: wx.TreeEvent):
        #drag_tree_item_id = evt.GetItem()
        #self._drag_tree_item_id = drag_tree_item_id
        #color = wx.ColourDatabase().FindColour("CYAN")
        #self.SetItemBackgroundColour(drag_tree_item_id, color)

        #print(f'{evt} begin drag')
        #evt.Allow()
        evt.Skip()

    def _on_tree_end_drag(self, evt):
        #print(f'{evt} end drag')
        #if self.drag_tree_item_id is not None:
        #    self.SetItemBackgroundColour(self.drag_tree_item_id, None)
        # не работающая функция
        evt.Skip()

    def _on_tree_item_begin_edit(self, evt: wx.TreeEvent):
        #print(f'{evt} begin edit')
        evt.Skip()

    def _on_tree_item_end_edit(self, evt: wx.TreeEvent):
        tree_item_id = evt.GetItem()
        self._last_item_id = tree_item_id
        self._sort(tree_item_id)
        #self.EnsureVisible(tree_item_id)
        evt.Skip()

    def _on_tree_item_deleted(self, evt: wx.TreeEvent):
        data_obj = self.GetItemData(evt.GetItem())
        if data_obj in self._items.keys():
            del self._items[data_obj]
            self._sort(evt.GetItem())

    def _on_tree_selected(self, evt: wx.TreeEvent):
        #print(f'{evt} selected')
        sel_objs = []
        if self._multiple_selection:
            dragging_tree_item_ids = self.GetSelections()
            for tree_item_id in dragging_tree_item_ids:
                sel_objs.append(self.GetItemData(tree_item_id))
        else:
            dragging_tree_item_id = self.GetSelection()
            sel_objs.append(self.GetItemData(dragging_tree_item_id))

        if self.on_selection_changed:
            self.on_selection_changed(sel_objs)
        evt.Skip()

    def _on_tree_item_activated(self, evt: wx.TreeEvent):
        if self.on_item_dclick:
            tree_item_id = evt.GetItem()
            item = self.GetItemData(tree_item_id)
            if item is not None:
                self.on_item_dclick(item)
        evt.Skip()

    def _on_destroy(self, _evt:wx.WindowDestroyEvent):
        #if event.GetWindow().__class__.__name__ == self.__class__.__name__:
        # self.Unbind(wx.EVT_LEFT_UP, self.OnMouseLeftUp)
        # Warning: необходимо отвязать события, иначе происходит ошибка во внутренней структуре C-кода компонента
        #print(f'{self}  window destroy BasicTree')
        self.Unbind(wx.EVT_TREE_DELETE_ITEM, handler=self._on_tree_item_deleted)
        self.Unbind(wx.EVT_TREE_SEL_CHANGED, handler=self._on_tree_selected)
        self.Unbind(wx.EVT_TREE_ITEM_ACTIVATED, handler=self._on_tree_item_activated)

    def add_item(self, item: Any, parent_item: Any, label: str, image: str='', image_expand:str = ''):
        #freezed = self.IsFrozen()
        #if not freezed:
        #    self.Freeze()
        if image and not image_expand:
            image_expand = image
        if item in self._items.keys():
            mlogger.error(f'{self} ошибка добавления {item}, такой элемент уже существует')
            #if not freezed:
            #    self.Thaw()
            return
        if parent_item is None:
            tree_item_id = self.AppendItem(self._root_item,label, self._image_list.get_index(image,True), -1, item)
            self.SetItemImage(tree_item_id, self._image_list.get_index(image_expand,True), wx.TreeItemIcon_Expanded)
            #self.SetItemDropHighlight(tree_item_id, True)
            self._items[item] = tree_item_id
            self._sort(tree_item_id)
            #self.EnsureVisible(tree_item_id)

        elif parent_item in self._items.keys():
            tree_item_id = self._items[parent_item]
            new_tree_item_id = self.AppendItem(tree_item_id, label, self._image_list.get_index(image, True), -1, item)
            self.SetItemImage(new_tree_item_id, self._image_list.get_index(image_expand, True), wx.TreeItemIcon_Expanded)
            #self.SetItemDropHighlight(new_tree_item_id, True)
            self._items[item] = new_tree_item_id
            self._sort(new_tree_item_id)
            #self.EnsureVisible(new_tree_item_id)
        #if not freezed:
        #    self.Thaw()

    def clear(self):
        self.DeleteChildren(self._root_item)
        self._items.clear()

    def write_item(self, item: Any, label: str, image: str='', image_expand:str = ''):
        #freezed = self.IsFrozen()
        #if not freezed:
        #    self.Freeze()
        if image and not image_expand:
            image_expand = image
        if item in self._items.keys():
            tree_item_id = self._items[item]
            self.SetItemText(tree_item_id, label)
            self.SetItemImage(tree_item_id, self._image_list.get_index(image,True), wx.TreeItemIcon_Normal)
            self.SetItemImage(tree_item_id, self._image_list.get_index(image_expand, True), wx.TreeItemIcon_Expanded)
            self._sort(tree_item_id)
        else:
            mlogger.error(f'{self} элемент {item} не найден в items')
        #if not freezed:
        #    self.Thaw()


    def is_item_exists(self, item: Any):
        return item in self._items.keys()


    def delete_item(self, item: Any, with_children: bool):
        #freezed = self.IsFrozen()
        #if not freezed:
        #    self.Freeze()
        if item in self._items.keys():
            tree_item_id = self._items[item]
            if with_children:
                self.DeleteChildren(tree_item_id)
            if self.GetChildrenCount(tree_item_id)==0:
                self.Delete(tree_item_id)
            else:
                mlogger.error(f'{self} элемент {item} невозможно удалить элемент, у него есть потомки')
            self._sort(tree_item_id)
        else:
            mlogger.error(f'{self} элемент {item} не найден в items')
        #if not freezed:
        #    self.Thaw()

    def get_parent_item(self, item: Any):
        if item in self._items.keys():
            cur_tree_item_id = self._items[item]
            tree_item_parent_id: wx.TreeItemId = self.GetItemParent(cur_tree_item_id)
            if tree_item_parent_id is not None and tree_item_parent_id.IsOk():
                return self.GetItemData(tree_item_parent_id)
        return None

    def get_children(self, item: Any):
        children_items = []
        if item in self._items.keys():
            cur_tree_item_id: wx.TreeItemId = self._items[item]
            cur_tree_item_id, cookie = self.GetFirstChild(cur_tree_item_id)
            while cur_tree_item_id.IsOk():
                children_items.append(self.GetItemData(cur_tree_item_id))
                cur_tree_item_id, cookie = self.GetNextChild(cur_tree_item_id, cookie)
        return children_items


    def rename_item(self, item: Any, label: str):
        if item in self._items.keys():
            tree_item_id = self._items[item]
            self.SetItemText(tree_item_id, label)
            self._last_item_id = tree_item_id
            self._sort(tree_item_id)
            #self.EnsureVisible(tree_item_id)
        else:
            mlogger.error(f'{self} элемент {item} не найден в items')

    def get_tree_item_id(self, item: Any):
        if item in self._items.keys():
            return self._items[item]
        return None


    def get_selected_items(self):
        sel_objects = []
        if self._multiple_selection:
            dragging_tree_item_ids = self.GetSelections()
            for tree_item_id in dragging_tree_item_ids:
                sel_objects.append(self.GetItemData(tree_item_id))
        else:
            dragging_tree_item_id = self.GetSelection()
            sel_objects.append(self.GetItemData(dragging_tree_item_id))
        return sel_objects


    def have_item(self, item: Any):
        return item in self._items.keys()

    def get_items(self):
        return list(self._items.keys())

    def add_bitmap(self, image_name: str, bitmap: str):
        self._image_list.add(image_name, bitmap)

    def set_item_bitmap(self, item: Any, bitmap: str):
        item_info = BasicTree.TreeItemInfo()
        item_info.image = bitmap
        self.set_item_state(item, item_info)

    def set_item_state(self, item: Any, item_info: TreeItemInfo):
        if item in self._items.keys():
            tree_item_id = self._items[item]
            self.SetItemTextColour(tree_item_id, item_info.text_color)
            self.SetItemBackgroundColour(tree_item_id, item_info.background_color)
            if item_info.is_bold is None:
                item_info.is_bold = False
            self.SetItemBold(tree_item_id, item_info.is_bold)
            if item_info.drop_highlight is None:
                item_info.drop_highlight = False
            self.SetItemDropHighlight(tree_item_id, item_info.drop_highlight)
            if item_info.font is None:
                item_info.font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
            self.SetItemFont(tree_item_id, item_info.font)
            self.SetItemTextColour(tree_item_id, item_info.text_color)
            self.SetItemImage(tree_item_id, self._image_list.get_index(item_info.image, True), wx.TreeItemIcon_Normal)
            self.SetItemImage(tree_item_id, self._image_list.get_index(item_info.image_selected, True), wx.TreeItemIcon_Selected)
            self.SetItemImage(tree_item_id, self._image_list.get_index(item_info.image_expanded, True), wx.TreeItemIcon_Expanded)
            self.SetItemImage(tree_item_id, self._image_list.get_index(item_info.image_selected_expanded, True), wx.TreeItemIcon_SelectedExpanded)

    def select_items(self, items: List[Any]):
        if items:
            tree_item_ids = []
            for item in items:
                if item in self._items.keys():
                    tree_item_id = self._items[item]
                    if tree_item_id.IsOk():
                        tree_item_ids.append(tree_item_id)
            if tree_item_ids:
                if self._multiple_selection:
                    self.UnselectAll()
                    for tree_item_id in tree_item_ids:
                        self.SelectItem(tree_item_id, True)
                else:
                    self.UnselectAll()
                    self.SelectItem(tree_item_ids[0], True)

class BasicInfoBar(wx.InfoBar):
    _can_be_closed: bool
    _buttons: Dict[str, Callable]
    _button_ids: Dict[int, str]
    def __init__(self, parent: Union[BasicPanel, 'BasicWindow', 'BasicDialog'], can_be_closed: bool = True):
        wx.InfoBar.__init__(self, parent)
        self.Bind(wx.EVT_BUTTON, self._on_button)
        self._can_be_closed = can_be_closed
        self._buttons = {}
        self._button_ids = {}
        self.SetShowHideEffects(wx.SHOW_EFFECT_NONE, wx.SHOW_EFFECT_NONE)

    def add_button(self, label: str, callback: Callable):
        button_id = None
        for key, val in self._button_ids.items():
            if val == label:
                button_id = key
        if label not in self._buttons.keys():
            self._buttons[label] = callback
            if button_id is None:
                button_id = wx.NewId()
                self._button_ids[button_id] = label
            self.AddButton(button_id, label)
        else:
            mlogger.error(f'{self} невозможно добавить кнопку. {label} уже добавлена')


    def clear_buttons(self):
        for bnt_id in self._button_ids.keys():
            self.RemoveButton(bnt_id)
        self._buttons.clear()

    def have_button(self, label:str):
        return label in self._buttons.keys()

    def _on_button(self, evt: wx.CommandEvent):
        #print(evt.GetId())
        #self.RemoveButton(evt.GetId())
        if evt.GetId() in self._button_ids.keys():
            self._buttons[self._button_ids[evt.GetId()]]()
            return
            #evt.Skip()
        if wx.ID_AUTO_LOWEST <=evt.GetId() <= wx.ID_AUTO_HIGHEST:
            if self._can_be_closed:
                evt.Skip()
        else:
            evt.Skip()

    def show_message(self, msg: str, icon: int, can_close: bool):
        self._can_be_closed = can_close
        if icon not in [wx.ICON_NONE, wx.ICON_INFORMATION, wx.ICON_QUESTION, wx.ICON_WARNING, wx.ICON_ERROR]:
            icon = wx.ICON_NONE
        if msg is None:
            msg = ''
        if type(msg)!=str:
            msg = str(msg)
        self.ShowMessage(msg, icon)

    def hide(self):
        self.Dismiss()


class BasicNotebook(wx.Notebook):
    _pages: Dict[str, Union[wx.Frame, wx.Panel]] = {}
    _pages_nums: Dict[str, int] = {}
    _rescale_size: wx.Size
    _registered_on_changed: List[Callable[[str, str,],None]] = []
    _image_list: ImageList
    _parent: Any
    def __init__(self, parent: Union[wx.Frame, wx.Panel, wx.Dialog], image_size_list: wx.Size):
        self._parent = parent
        wx.Notebook.__init__(self, parent, wx.ID_ANY, size=wx.DefaultSize, style=
                             wx.BK_DEFAULT
                             #wx.BK_TOP
                             #|wx.BK_BOTTOM
                             #wx.BK_LEFT
                             #wx.BK_RIGHT
                             | wx.NB_MULTILINE
                             )

        self._rescale_size = image_size_list
        self._image_list = ImageList(wx.Size(image_size_list.GetWidth(), image_size_list.GetHeight()))
        self._set_image_list(self._image_list)
        self._pages = {}
        self._pages_nums = {}
        self._registered_on_changed = []

        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_page_changed)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGING, self.on_page_changing)

    def set_page_image(self, page_name: str, image_name: Optional[str]):
        if page_name not in self._pages.keys():
            mlogger.warning(f"{self} Страница с именем \"{page_name}\" не найдена (set page image)")
            return
        page_num = 0
        for cur_page_name, page_num_i in self._pages.items():
            if page_name == cur_page_name:
                page_num = page_num_i
        if image_name is None:
            self.SetPageImage(page_num,-1)
        else:
            image_index = self._image_list.get_index(image_name)
            if image_index is not None:
                self.SetPageImage(page_num, image_index)

    def _set_image_list(self, image_list: ImageList):
        self._image_list = image_list
        self.AssignImageList(self._image_list.image_list)


    def clear(self):
        # ВНИМАНИЕ! Если удалять страницу через delete_page, то будет вызвано событие EVT_NOTEBOOK_PAGE_CHANGED
        # что может привести к странным последствиям в виде выбора другой страницы, которая уже была удалена вроде ???
        # короче очередной глюк wxWidgets
        self._pages.clear()
        self._pages_nums.clear()
        self.DeleteAllPages()

    def delete_page(self, page_name: str):
        found_del_page = False
        del_index = -1
        for cur_page_name, cur_index in self._pages_nums.items():
            if cur_page_name == page_name:
                del_index = cur_index
                found_del_page = True
            if found_del_page:
                self._pages_nums[cur_page_name] -= 1
        if found_del_page:
            del self._pages_nums[page_name]
            del self._pages[page_name]
            # непосредственное удаление страницы должно происходить в конце,
            # так как DeletePage вызывает on_page_changed, и все связанные с этим события могут привести к неверному поиску страницы
            self.DeletePage(del_index)

        else:
            mlogger.error(f"{self} Страница \"{page_name}\" не найдена")

    def add_page(self, page_name: str, panel: Union[wx.Panel, wx.lib.scrolledpanel.ScrolledPanel]):
        if page_name in self._pages.keys():
            mlogger.warning(f"{self} Страница с именем \"{page_name}\" уже существует")
            return

        #if image is None:
        self.AddPage(panel, page_name)
        #self._image_list.Add(wx.Bitmap(self._rescale_size.width, self._rescale_size.height))
        if __debug__:
            mlogger.debug(f"{self} Страница \"{page_name}\" добавлена без картинки")
        #else:
        #    self._image_list.Add(rescale_image_to_bitmap(image, custom_size=self._rescale_size))
        #    if __debug__:
        #        mlogger.debug("Страница \"{0}\" добавлена с картинкой".format(page_name))
        #    cur_image_id = self.GetPageCount()
        #    self.AddPage(panel, page_name, imageId=cur_image_id)
        self._pages[page_name] = panel
        self._pages_nums[page_name] = self.GetPageCount()-1

    def select_page(self, page_name: str):
        if page_name not in self._pages.keys():
            mlogger.warning(f"{self} Страница с именем \"{page_name}\" не найдена (select page)")
            return
        for cur_page_name, page_num in self._pages_nums.items():
            if page_name == cur_page_name:
                self.ChangeSelection(page_num)
                #cmd_evt = wx.BookCtrlEvent(wx.wxEVT_NOTEBOOK_PAGE_CHANGED, self.GetId())
                #cmd_evt.SetEventObject(self)
                #cmd_evt.SetOldSelection(-1)
                #cmd_evt.SetSelection(page_num)
                #wx.PostEvent(self, cmd_evt)

    def have_page(self, page_name: str):
        return page_name in self._pages.keys()

    def on_page_changed(self, event: wx.BookCtrlEvent):
        if self == event.GetEventObject():
            old = event.GetOldSelection()
            new = event.GetSelection()
            #sel = self.GetSelection()
            old_name = ""
            new_name = ""
            for page_name, page in self._pages_nums.items():
                if old == page:
                    old_name = page_name
                if new == page:
                    new_name = page_name
            if __debug__:
                mlogger.debug(f"{self} Окончание перехода со страницы \"{old_name}\" на страницу \"{new_name}\"")
            for func in self._registered_on_changed:
                func(old_name, new_name)
        event.Skip()

    def on_page_changing(self, event: wx.BookCtrlEvent):
        if self == event.GetEventObject():
            sel = self.GetSelection()
            sel_name = ""
            for page_name, page in self._pages_nums.items():
                if sel == page:
                    sel_name = page_name
            if __debug__:
                mlogger.debug(f"{self} Начало перехода со страницы \"{sel_name}\"")
        event.Skip()


    def register_on_changed(self, func: Callable[[str, str,],None]):
        self._registered_on_changed.append(func)

    def unregister_on_changed(self, func: Callable[[str, str,],None]):
        if func in self._registered_on_changed:
            self._registered_on_changed.remove(func)

    def get_selected_page_name(self) -> str:
        cur_page = self.GetSelection()
        for page_name, page in self._pages_nums.items():
            if cur_page == page:
                return page_name
        return None

    def get_selected_page(self):
        cur_page = self.GetSelection()
        for page_name, page in self._pages_nums.items():
            if cur_page == page:
                if page_name in self._pages.keys():
                    return self._pages[page_name]
        return None

    def get_page_instances(self):
        return list(self._pages.values())

    def get_page_names(self):
        return list(self._pages.keys())

    def get_page(self, name: str):
        if name in self._pages.keys():
            return self._pages[name]
        return None

    def get_control_page_name(self, control: Any)->Optional[str]:
        for name, c in self._pages.items():
            if c == control:
                return name
        return None




class BasicDialog(wx.Dialog, BasicWxCommandListener, EventSubscriber, WxEvents):
    ini_file: Optional[configparser.ConfigParser]
    window_name: str
    sizeable: bool
    _parent: Any
    close_callback: Optional[Callable]
    def __init__(self, parent:Union[wx.Frame, wx.Panel, wx.ScrolledCanvas, wx.Dialog], title: str, icon_path: Optional[Union[str, wx.Bitmap]], pos: wx.Point, size: wx.Size, ini_config: configparser.ConfigParser, sizeable: bool, style: int = wx.DEFAULT_DIALOG_STYLE):
        self._parent = parent
        wx.Dialog.__init__(self)
        EventSubscriber.__init__(self)
        BasicWxCommandListener.__init__(self, self)
        WxEvents.__init__(self)
        self.close_callback = None
        self.ini_file = ini_config
        self.window_name = title
        self.sizeable  = sizeable
        if sizeable:
            style = style | wx.RESIZE_BORDER

        self.Create(parent, wx.NewId(), title, pos, size, style)
        self.SetTitle(title)
        if icon_path is not None:
            if type(icon_path) == wx.Bitmap:
                try:
                    icon = wx.Icon()
                    icon.CopyFromBitmap(icon_path)
                    self.SetIcon(icon)
                except Exception as ex:
                    mlogger.error(f"{self} ошибка загрузки иконки приложения: {ex}")
            elif type(icon_path) == str and os.path.exists(icon_path):
                self.SetIcon(wx.Icon(icon_path))
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_SHOW, self._on_show)
        if size:
            self.SetSize(size)
            self.SendSizeEvent()


        if self.ini_file:
            self.load_state()


        if __debug__:
            mlogger.debug(f'{self} создание: {title}')


    def load_state(self):
        try:
            if self.ini_file is not None:
                if self.ini_file.has_section(self.window_name):
                    pos_x = int(self.ini_file[self.window_name]["posx"])
                    pos_y = int(self.ini_file[self.window_name]["posy"])
                    size_w = int(self.ini_file[self.window_name]["sizew"])
                    size_h = int(self.ini_file[self.window_name]["sizeh"])
                    self.SetPosition(wx.Point(pos_x, pos_y))
                    if self.sizeable:
                        self.SetSize(wx.Size(size_w, size_h))
        except Exception as ex:
            mlogger.error(f"{self} Ошибка загрузки файла конфигурации {ex}")

    def save_state(self):
        if self.ini_file is not None:
            try:
                pos_x = self.GetPosition()[0]
                pos_y = self.GetPosition()[1]
                size_w = self.GetSize()[0]
                size_h = self.GetSize()[1]
                if self.ini_file is not None:
                    if not self.ini_file.has_section(self.window_name):
                        self.ini_file.add_section(self.window_name)
                    self.ini_file[self.window_name]["posx"] = str(pos_x)
                    self.ini_file[self.window_name]["posy"] = str(pos_y)
                    self.ini_file[self.window_name]["sizew"] = str(size_w)
                    self.ini_file[self.window_name]["sizeh"] = str(size_h)
            except Exception as ex:
                mlogger.error(f"{self} сохранения файла конфигурации {ex}")

    def _on_close(self, evt: wx.CloseEvent):
        if self.ini_file:
            self.save_state()
        self.on_close_dialog()
        evt.Skip()


    def _on_show(self, evt: wx.ShowEvent):
        if not evt.IsShown():
            if self.ini_file:
                self.save_state()
            self.on_close_dialog()
        evt.Skip()


    def on_close_dialog(self):
        pass


class BasicProgressDialog(BasicDialog): #BasicWindow, EventSubscriber):
    """ВНИМАНИЕ: любые попытки использовать потоки ни к чему хорошему не привели. Обновление только по событию"""
    #modal = None
    def __init__(self, parent: Union[wx.Frame, wx.Panel, wx.Dialog, wx.Control, wx.grid.Grid], window_name: str, size: wx.Size = wx.Size(200, 10)):
        self._parent = parent
        style = wx.CAPTION | wx.FRAME_NO_TASKBAR | wx.FRAME_FLOAT_ON_PARENT
        BasicDialog.__init__(self, parent, window_name, None, wx.DefaultPosition, size, None, False, style | wx.PD_APP_MODAL | wx.FRAME_FLOAT_ON_PARENT | wx.STAY_ON_TOP)
        self.ToggleWindowStyle(wx.STAY_ON_TOP)
        EventSubscriber.__init__(self)
        wnd_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_panel = wx.Panel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        wnd_sizer.Add(self.main_panel, 1, wx.EXPAND, 0)
        self.main_panel.SetSizer(self.main_sizer)
        self.SetSizer(wnd_sizer)
        self.SetMinSize(size)
        self.Layout()
        self.CenterOnParent()
        new_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_panel.SetSizer(new_sizer)
        self.progress = wx.ActivityIndicator(self.main_panel)
        new_sizer.Add(self.progress, 1, wx.ALIGN_CENTER_HORIZONTAL, 0)
        self.progress.Start()
        self.Layout()







class BasicWindow(wx.Frame, BasicWxCommandListener, WxEvents):
    ini_file: Optional[configparser.ConfigParser]
    window_name: str
    #commands_list: List[WxCommand]
    auto_hide: bool
    parent: Optional[wx.Frame]
    _close_callback: Optional[Callable[[wx.CloseEvent],None]]
    modal: Optional[wx.WindowDisabler]
    _parent: Any
    _progress_indicator: wx.ActivityIndicator
    def __init__(self, parent: Optional[Union[wx.Frame, Any]], window_name: str, icon_path: Optional[str], ini_file: Optional[configparser.ConfigParser], pos: Optional[wx.Point] = None, size: Optional[wx.Size] = None, sizeable: bool = True, centered: bool = False, auto_hide: bool = False, style: int = wx.DEFAULT_FRAME_STYLE):
        # style = wx.DEFAULT_FRAME_STYLE
        self._parent = parent
        self.ini_file = ini_file
        self.window_name = window_name
        self.auto_hide = auto_hide
        self.parent = parent
        self._close_callback = None
        self.modal = None

        if not sizeable:
            style = style & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        if size is None:
            size = wx.Size(100, 100)

        if pos is None:
            pos = wx.DefaultPosition

        if parent is not None:
            wx.Frame.__init__(self, parent, id=wx.ID_ANY, title=window_name, pos=pos, size=size, style=style)
        else:
            wx.Frame.__init__(self, None, id=wx.ID_ANY, title=window_name, pos=pos, size=size, style=style)
        BasicWxCommandListener.__init__(self, self)
        WxEvents.__init__(self)

        if window_name is None or len(window_name) < 1:
            mlogger.error(f"{self} Ошибка загрузки BasicWindow. Имя не задано")
            return

        if icon_path is not None:
            if os.path.exists(icon_path):
                try:
                    self.SetIcon(wx.Icon(icon_path))
                except Exception as ex:
                    mlogger.error(f"{self} Ошибка загрузки {self.GetTitle()}. Невозможно установить иконку {ex}")

        try:
            if self.ini_file is not None:
                if self.ini_file.has_section(self.window_name):
                    size_w = 500
                    size_h = 100
                    if size is not None:
                        size_w = size[0]
                        size_h = size[1]
                    if sizeable:
                        size_w = int(ini_file[self.window_name]["sizew"])
                        size_h = int(ini_file[self.window_name]["sizeh"])
                    if not centered:
                        pos_x = int(ini_file[self.window_name]["posx"])
                        pos_y = int(ini_file[self.window_name]["posy"])
                    else:
                        screen_size = wx.DisplaySize()
                        pos_x = (screen_size[0] - size_w) / 2
                        pos_y = (screen_size[1] - size_h) / 2
                    self.SetPosition(wx.Point(pos_x, pos_y))
                    self.SetSize(wx.Size(size_w, size_h))
        except Exception as ex:
            mlogger.error(f"{self} Ошибка загрузки файла конфигурации {window_name} {ex}")

        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_ACTIVATE, self._on_lost_focus)
        #func_names = WxEvents.get_debounced_names(type(self))
        #WxEvents.register(type(self), func_names)
        self._progress_indicator = wx.ActivityIndicator(self)
        self._progress_indicator.CenterOnParent()
        self._progress_indicator.Hide()
        if __debug__:
            mlogger.debug(f'{self} создание: {window_name}')


    def show_simple_progress(self, show: bool):
        if show:
            sizer: wx.BoxSizer = self.GetSizer()
            self.__global_sizer = sizer
            for i in range(sizer.GetItemCount()):
                sizer.Hide(i)
            self._progress_indicator.Show()
            self._progress_indicator.Start()


        else:
            sizer: wx.BoxSizer = self.GetSizer()
            for i in range(sizer.GetItemCount()):
                sizer.Show(i)
            self._progress_indicator.Hide()
            self._progress_indicator.Stop()


    @staticmethod
    def long_running(func):
        """
        Декоратор для выполнения долгих задач
        :return:
        """
        def wrap(*args, **kwargs):
            # noinspection PyTypeChecker
            t = threading.Thread(target=func,args=args, kwargs=kwargs)
            t.start()
        return wrap

    def save_state(self):
        try:
            pos_x = self.GetPosition()[0]
            pos_y = self.GetPosition()[1]
            size_w = self.GetSize()[0]
            size_h = self.GetSize()[1]
            # iniFile.read(iniFileName)
            if self.ini_file is not None:
                if not self.ini_file.has_section(self.window_name):
                    self.ini_file.add_section(self.window_name)
                self.ini_file[self.window_name]["posx"] = str(pos_x)
                self.ini_file[self.window_name]["posy"] = str(pos_y)
                self.ini_file[self.window_name]["sizew"] = str(size_w)
                self.ini_file[self.window_name]["sizeh"] = str(size_h)
                if __debug__:
                    mlogger.debug(f'{self} сохранение: {self.GetTitle()}')
        except Exception as ex:
            mlogger.error(f"{self} Ошибка сохранения файла конфигурации {self.GetTitle()} {ex}")

    def register_close_callback(self, c: Callable[[wx.CloseEvent], None]):
        self._close_callback = c

    def on_close(self, event: wx.CloseEvent):
        #event.Skip() # - эта функция вызывает дичь,
        # в принципее много что здесь вызывает дичь
        if self == event.GetEventObject():
            if self.IsMaximized():
                self.Maximize(False)
            self.save_state()
            if __debug__:
                mlogger.debug(f'{self} закрытие {self.GetTitle()}')
            if self._close_callback is not None:
                self._close_callback(event)
            if not event.GetVeto():
                self.Restore()
                self.Destroy()
            #else:
            #    evt.Skip() # возможно будет дичь

    def _on_lost_focus(self, event: wx.ActivateEvent):
        if event.GetEventObject() == self:
            if self.auto_hide:
                if not event.GetActive():
                    self.Close(True)
            if not event.GetActive():
                self.on_lost_focus()
        event.Skip()

    def on_lost_focus(self):
        pass


    def stay_on_top(self, stay_on_top: bool):
        if stay_on_top:
            self.SetWindowStyle(self.GetWindowStyle() | wx.STAY_ON_TOP)
        else:
            self.SetWindowStyle(self.GetWindowStyle() & ~wx.STAY_ON_TOP)


class BasicPopupWindow(wx.PopupTransientWindow):

    _panel: wx.Panel
    _parent: Any
    _close_any_key: bool
    def __init__(self, parent: Union[wx.Frame, wx.Window, wx.Panel], close_any_key: bool):
        wx.PopupTransientWindow.__init__(self, parent, flags=wx.BORDER_RAISED | wx.PU_CONTAINS_CONTROLS | wx.PD_APP_MODAL)
        self._parent = parent
        self._close_any_key = close_any_key


        sizer = wx.BoxSizer(wx.VERTICAL)
        self._panel = wx.Panel(self)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_pressed)

        sizer.Add(self._panel, 1, wx.ALL | wx.EXPAND, 0)
        self._main_sizer = wx.BoxSizer(wx.VERTICAL)
        self._panel.SetSizer(self._main_sizer)
        self.SetSizer(sizer)
        self.Fit()
        self.Layout()

    def get_root_item(self):
        return self._panel

    def add_control(self, ctrl):
        self._main_sizer.Add(ctrl, 0, wx.EXPAND | wx.ALL, 0)
        self._main_sizer.Layout()
        size = self._main_sizer.GetSize()
        best_size = self.GetBestSize()
        self.SetSize(best_size)
        self.Layout()

    def _on_key_pressed(self, event: wx.KeyEvent):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Dismiss()
        if self._close_any_key:
            self.Dismiss()
        event.Skip()



class BasicButton(wx.Button, EventPublisher):
    button_id: int
    _standart_color: wx.Colour
    _highligted_color: wx.Colour
    _parent: Any
    def __init__(self, parent: Union[BasicWindow, BasicPanel, wx.Panel], button_id: int = wx.ID_ANY, label: str = '', pos: wx.Point = wx.DefaultPosition, size: wx.Size = wx.DefaultSize, style:int = 0, validator: wx.Validator = wx.DefaultValidator, name:str=''):
        self._parent = parent
        self.button_id = button_id
        wx.Button.__init__(self, parent, button_id,label,pos, size, style, validator, name)
        EventPublisher.__init__(self)
        self._standart_color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_MENU)
        self._highligted_color =  wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRADIENTACTIVECAPTION)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_hover)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_unhover)
        self.Bind(wx.EVT_BUTTON, self._on_button)
        self.SetBackgroundColour(self._standart_color)

    def _on_hover(self, evt: wx.MouseEvent):

        self.SetBackgroundColour(self._highligted_color)
        evt.Skip()

    def _on_unhover(self, evt: wx.MouseEvent):
        self.SetBackgroundColour(self._standart_color)
        evt.Skip()

    def _on_button(self, _evt: wx.CommandEvent):
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))

    @staticmethod
    def get_value(_self):
        return None
class CalendarPopup(wx.ComboPopup, EventPublisher):
    cal: Optional[wx.adv.CalendarCtrl]
    parent: 'BasicDatePicker'
    cur_selected_date: Optional[datetime.datetime]
    value: Any
    curitem: Any

    _parent: Any
    def __init__(self, parent: 'BasicDatePicker'):
        self._parent = parent
        EventPublisher.__init__(self)
        wx.ComboPopup.__init__(self)
        self.is_dismissed = False
        self.parent = parent
        self.cal = None
        self.cur_selected_date = None


    # This is called immediately after construction finishes.  You can
    # use self.GetCombo if needed to get to the ComboCtrl instance.
    def Init(self):
        self.value = -1
        self.curitem = -1


    # Create the popup child control.  Return true for success.
    def Create(self, parent):
        self.cal = wx.adv.CalendarCtrl(parent, style=wx.adv.CAL_MONDAY_FIRST ^ wx.adv.CAL_SHOW_SURROUNDING_WEEKS)
        #self.cal.Bind(wx.adv.EVT_CALENDAR_SEL_CHANGED, self.on_date_changed) # запрещено использовать, Dismiss в этом коде будет уходить в бесконечный цикл
        #self.cal.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)
        self.cal.Bind(wx.adv.EVT_CALENDAR_SEL_CHANGED, self.on_day_clicked)
        return True

    def on_day_clicked(self, _evt: wx.adv.CalendarEvent):

        self.parent.set_value(_wxdate_to_date(_evt.GetDate()))
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self.parent))
        # noinspection PyProtectedMember
        self.parent._update()
        self.parent.Update()
        self.parent.Refresh()
        _evt.Skip()


    def GetStringValue(self):
        return ""

    # Return the widget that is to be used for the popup
    def GetControl(self):
        return self.cal

    def OnPopup(self):
        #self.cal.SetFocus()
        #self.cal.AcceptsFocus()
        self.is_dismissed = False
        # noinspection PyProtectedMember
        self.parent._correct_date()
        self.parent.Refresh()
        self.parent.Update()
        wx.Yield()
        wx.ComboPopup.OnPopup(self)

    # Called when popup is dismissed
    def OnDismiss(self):
        self.is_dismissed = True
        #window = wx.Window.FindFocus()
        wx.ComboPopup.OnDismiss(self)

    def PaintComboControl(self, dc, rect):
        wx.ComboPopup.PaintComboControl(self, dc, rect)

    # Receives key events from the parent ComboCtrl.  Events not
    # handled should be skipped, as usual.
    def OnComboKeyEvent(self, event):
        wx.ComboPopup.OnComboKeyEvent(self, event)

    def OnComboDoubleClick(self):
        wx.ComboPopup.OnComboDoubleClick(self)

    def GetAdjustedSize(self, min_width, pref_height, max_height):
        #self.log.write("ListCtrlComboPopup.GetAdjustedSize: %d, %d, %d" % (minWidth, prefHeight, maxHeight))
        #return wx.ComboPopup.GetAdjustedSize(self, minWidth, prefHeight, maxHeight)
        if self.cal is not None:
            return self.cal.GetBestSize()
        return wx.Size(150,150)

    # Return true if you want delay the call to Create until the popup
    # is shown for the first time. It is more efficient, but note that
    # it is often more convenient to have the control created
    # immediately.
    # Default returns false.
    def LazyCreate(self):
        #self.log.write("ListCtrlComboPopup.LazyCreate")
        return wx.ComboPopup.LazyCreate(self)

class BasicDatePicker(wx.ComboCtrl, EventPublisher):
    # noinspection SpellCheckingInspection
    dtNormalImg = '32:32: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:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABLT///////////////////////////////+0BAAAAAAN//////////////////////////////////8NAAAAABX//////////////////////////////////xUAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAVxP////////////////////////////////MWAAAAAA0rP0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NCMRAAAAAABA0VFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQBQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    dtHoverImg = '32:32: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vtnuocPfb5/F1+r4uLe11e//1e//lpaWlpaW1e//1e//M5DD////rq2t5/b/6Pb/8v3/WosAndEAnM4AnM4AWosA8v3/6Pf/5/b/3fL/naOl0ej7gq3PVYy4S4GqVI24a5vAfajJqMbc3vL/sLGy1e//1e//lpaWlpaW1e//1e//K43A////s7Ozr6+wsK+yt7TBV4wAWowAWYoAWYoAV4wAt7TBsbGzn6WpnKOqmKKqk52mZJS2////9fj85/H33ev00+Pwxt7vwsLCqqut1e//1e//lpaWlpaW1e//1e//Joq/////tbS08v3/8v3/9///ubbE/f//+v//+v//ubbE+P//6/n/1uv60Of5k56nwt3yeKG//P3/5/D32+nz0eLvxd3uu9Hiy8zNpqiq1e//1e//lpaWlpaW1e//1e//I4m+////tbW18fv/8fv/9P//tLS39f//8vv/8vv/tLS39v//5vP80uX0zOLzjpulvdjsob/U7vX63Or00eLvxd3uutXpusDE1dXWoaOm1e//1e//lpaWlpaW1e//1e//IIe9////tra29Pz/9Pz/9///s7S19///9Pz/9Pz/tLS2+f//6PP90eTxy+Hxjpulu9Xqu9Hh4e320uPwxd3uutXpub3BxMPE3N3fnZ+i1e//1e//lpaWlpaW1e//1e//G4S7////ubm6+v//+v///f//t7m6/f//+v//+v//uLm6////6vb+1+n1zuX0kJyottLo6PL51OTxxt7vutPlt7zAwcHCy8zN5ufmmZud1e//1e//lpaWlpaW1e//1e//F4O6////ubm6tre5tre5t7i6uLq8t7i6tre5tre5uLq8ubq7qK6znaavlqOslKCrYYmm2Oj0x9/xuMzatLa4v8DAycvL09TV7u/uk5WZ1e//1e//lpaWlpaW1e//1e//FIG4////////////////////////////////////////////8fn+4u342uj0t9HlZZ3ByNvstb3Ds7S0vr/AyMrK09PU3N3e+Pj5kJKV1e//1e//lpaWlpaW1e//1e//F3anEX+3DHy1C3u1C3u1C3u1C3u1C3u1C3u1C3u1C3u1DHy1DH22CX25YIWbh4uRjo2NjY+QjpCSjY+RjY+RjI6Qi42PioyOi42PjY+R1e//1e//lpaWlpaW1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//lpaWg4OD1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//1e//hYWFzMzMhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWF5+fnAQAAzMzMvr6+vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vLy8vr6+zMzMzMzM5+fn://///////////////////////////////////////////////////////////////////////////////////////7T///////////////////////////////+0////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////xP////////////////////////////////P/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////AP///////////////////////////////////////w==' # noqa
    # noinspection SpellCheckingInspection
    dtPressedImg = '32:32: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:////////////////////////////////////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//8ABLT///////////////////////////////+0BAD//wAN//////////////////////////////////8NAP//ABX//////////////////////////////////xUA//8AFv//////////////////////////////////FgD//wAW//////////////////////////////////8WAP//ABb//////////////////////////////////xYA//8AFv//////////////////////////////////FgD//wAW//////////////////////////////////8WAP//ABb//////////////////////////////////xYA//8AFv//////////////////////////////////FgD//wAW//////////////////////////////////8WAP//ABb//////////////////////////////////xYA//8AFv//////////////////////////////////FgD//wAW//////////////////////////////////8WAP//ABb//////////////////////////////////xYA//8AFv//////////////////////////////////FgD//wAW//////////////////////////////////8WAP//ABb//////////////////////////////////xYA//8AFv//////////////////////////////////FgD//wAW//////////////////////////////////8WAP//ABb//////////////////////////////////xYA//8AFv//////////////////////////////////FgD//wAW//////////////////////////////////8WAP//ABb//////////////////////////////////xYA//8AFv//////////////////////////////////FgD//wAVxP////////////////////////////////MWAP//AA0rP0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NCMRAA//8ABA0VFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQBQD/////////////////////////////////////////////AP///////////////////////////////////////w==' # noqa
    # noinspection SpellCheckingInspection
    dtDisabledImg = '32:32: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:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABLT///////////////////////////////+0BAAAAAAN//////////////////////////////////8NAAAAABX//////////////////////////////////xUAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAW//////////////////////////////////8WAAAAABb//////////////////////////////////xYAAAAAFv//////////////////////////////////FgAAAAAVxP////////////////////////////////MWAAAAAA0rP0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NCMRAAAAAABA0VFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQBQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==' # noqa

    _date: Optional[datetime.date]
    _date_delimiter: str = '.'
    _cur_cel:int = 0

    _day: Optional[int]
    _month: Optional[int]
    _year: Optional[int]

    _year_enter_count: int = 0

    _day_region: wx.Rect
    _month_region: wx.Rect
    _year_region: wx.Rect
    _should_clear_before_input: bool = False

    popup_callback: Optional[Callable]
    closeup_callback: Optional[Callable]

    cal: CalendarPopup


    _parent: Any
    def __init__(self, parent: Any, id_val: int = wx.ID_ANY, value: Any = '', pos: wx.Point = wx.DefaultPosition, size: wx.Size = wx.DefaultSize, style: int = wx.CB_DROPDOWN):
        self._parent = parent
        EventPublisher.__init__(self)
        #ComboCtrl(parent, id=ID_ANY, value=value, pos=DefaultPosition, size=DefaultSize, style=0, validator=DefaultValidator, name=ComboBoxNameStr)
        #style = wxCB_SIMPLE:
        #Creates a combobox with a permanently displayed list. Windows only.
        #wxCB_DROPDOWN:
        #Creates a combobox with a drop-down list. MSW and Motif only.
        #wxCB_READONLY:
        #A combobox with this style behaves like a wxChoice (and may look in the same way as well, although this is platform-dependent), i.e. it allows the user to choose from the list of options but doesn't allow to enter a value not present in the list.
        #wxCB_SORT:
        #Sorts the entries in the list alphabetically.
        #wxTE_PROCESS_ENTER:
        #The control will generate the event wxEVT_TEXT_ENTER (otherwise pressing Enter key is either processed internally by the control or used for navigation between dialog controls).
        self._cur_cel = 0
        self._day = None
        self._month = None
        self._year = None

        wx.ComboCtrl.__init__(self,parent,id_val, value, pos, size, style, wx.DefaultValidator, '')
        #wx.ComboCtrl.__init__(self,parent,id_val, value, pos, size, style, wx.DefaultValidator, '')
        b1 = _base64_str_to_image(self.dtNormalImg).Scale(GuiWidgetSettings.datetime_icon_size, GuiWidgetSettings.datetime_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap()
        b2 = _base64_str_to_image(self.dtPressedImg).Scale(GuiWidgetSettings.datetime_icon_size, GuiWidgetSettings.datetime_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap()
        b3 = _base64_str_to_image(self.dtHoverImg).Scale(GuiWidgetSettings.datetime_icon_size, GuiWidgetSettings.datetime_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap()
        b4 = _base64_str_to_image(self.dtDisabledImg).Scale(GuiWidgetSettings.datetime_icon_size, GuiWidgetSettings.datetime_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap()
        self.popup_callback = None
        self.closeup_callback = None
        self.SetButtonBitmaps(b1, False, b2, b3, b4)
        self.cal = CalendarPopup(self)
        self.Bind(wx.EVT_COMBOBOX_DROPDOWN, self._on_popup)
        self.Bind(wx.EVT_COMBOBOX_CLOSEUP, self._on_close_up)


        self._day = None
        self._month = None
        self._year = None
        self._should_clear_before_input = True


        text_input = self.FindWindowByName('text', self)
        if text_input is not None:
            text_input.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_event)
            text_input.Bind(wx.EVT_CHAR, self._on_char)
        else:
            mlogger.error(f'{self} Повреждение компонента')


        #self.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_event)

        self.SetPopupControl(self.cal)
        self._date = None
        self._update()

        # Called immediately after the popup is shown

    def _set_date(self, d: Optional[datetime.date]):
        if d is not None:
            self._date = d
            self._day = self._date.day
            self._month = self._date.month
            self._year = self._date.year
        else:
            self._date = None
            self._day = None
            self._month = None
            self._year = None
        self._update()
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))

    def _on_popup(self, _e: wx.CommandEvent):
        self._should_clear_before_input = True
        self._correct_date()
        if self._date is not None:
            self.cal.cal.SetDate(_date_to_wxdate(self._date))
            self.cal.cal.Update()
            wx.Yield()
        if self.popup_callback is not None:
            self.popup_callback(_e)


    def _on_close_up(self, _e: wx.CommandEvent):
        if self.closeup_callback is not None:
            self.closeup_callback(_e)

    def _close_popup(self):
        if self.cal is not None:
            wx.CallAfter(self.HidePopup, True)

    def set_focus(self):
        text_input = self.FindWindowByName('text', self)
        if text_input is not None:
            text_input: wx.TextCtrl
            text_input.SetFocus()
            text_input.SetFocusFromKbd()
        self._should_clear_before_input = True
        self._cur_cel = 0
        self._select_item(0)



    def _update(self):
        if self._day is not None:
            day_str = f'{self._day:02}'
        else:
            day_str = '__'
        if self._month is not None:
            month_str = f'{self._month:02}'
        else:
            month_str = '__'
        if self._year is not None:
            year_str = f'{self._year:04}'
        else:
            year_str = '____'
        output_str = f'{day_str}.{month_str}.{year_str}'
        self.SetValue(output_str)
        point_region: wx.Size = self.GetTextExtent('.')
        self._day_region = wx.Rect(self.GetTextExtent(day_str))
        self._month_region= wx.Rect(self.GetTextExtent(month_str))
        self._year_region= wx.Rect(self.GetTextExtent(year_str))
        self._month_region.SetX(self._month_region.GetX() + self._day_region.GetX() + self._day_region.GetWidth() + point_region.GetWidth())
        self._year_region.SetX(self._year_region.GetX() + self._month_region.GetX() + self._month_region.GetWidth() + point_region.GetWidth())
        wx.CallAfter(self._select_item, self._cur_cel)

    def _on_mouse_event(self, evt: wx.MouseEvent):
        self._update()
        click_pos = evt.GetPosition()
        if click_pos.x<=self._day_region.GetX()+self._day_region.GetWidth():
            #text_input.SetInsertionPoint(0)
            self._cur_cel = 0
            self._should_clear_before_input = True
            wx.CallAfter(self._select_item, self._cur_cel)

        elif click_pos.x<=self._month_region.GetX()+self._month_region.GetWidth():
            #text_input.SetInsertionPoint(3)
            self._cur_cel = 1
            self._should_clear_before_input = True
            wx.CallAfter(self._select_item, self._cur_cel)

        elif click_pos.x>=self._month_region.GetX()+self._month_region.GetWidth():
            #text_input.SetInsertionPoint(6)
            self._cur_cel = 2
            self._should_clear_before_input = True
            wx.CallAfter(self._select_item, self._cur_cel)
        self._should_clear_before_input = True
        evt.Skip()

    def _select_item(self, item_no:int):
        if item_no == 0:
            #self.SetInsertionPoint(0)
            self.SetSelection(0,2)

        elif item_no == 1:
            #self.SetInsertionPoint(3)
            self.SetSelection(3, 5)

        elif item_no == 2:
            #self.SetInsertionPoint(6)
            self.SetSelection(6, 10)
        #self.SetFocus()
        self.Refresh()
        self.Update()

    def _correct_date(self):
        value_changed = False
        if self._day is not None:
            if self._day<=0:
                self._day = 1
                value_changed = True

            elif self._day>31:
                self._day = int(str(self._day)[0])
                value_changed = True
        if self._month is not None:
            if self._month<=0:
                self._month = 1
                value_changed = True
            elif self._month>12:
                self._month = int(str(self._month)[0])
                value_changed = True
        if self._year is not None:
            if self._year<=0:
                self._year = datetime.date.today().year
                value_changed = True
            #else:
            #    if self.year_enter_count == 2 and self.year<100:
            #        self.year = int(str(datetime.date.today().year)[0:2])*100 + self.year
            #        value_changed = True
        if self._day is not None and self._month is not None and self._year is not None:
            if calendar.monthrange(self._year, self._month)[1] < self._day:
                if self._cur_cel == 2:
                    self._day = calendar.monthrange(self._year, self._month)[1]
                    value_changed = True
                else:
                    self._year = None
                    value_changed = True
                    self._update()

        if self._day is not None and self._month is not None and self._year is not None:
            new_date = datetime.date(self._year, self._month, self._day)
            if self._date != new_date:
                self._date = new_date
                value_changed = True
            if hasattr(self, 'cal'):
                if self.cal is not None:
                    new_date = _date_to_wxdate(self._date)
                    if new_date:
                        self.cal.cal.SetDate(new_date)
                    else:
                        self._year = None
                        value_changed = True
            self._update()
        else:
            self._date = None
            value_changed = True

        self.Update()
        if value_changed:
            self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))

    def _on_char(self, evt: wx.KeyEvent):
        key_code = evt.GetKeyCode()
        if chr(key_code) in '0123456789':
            entered_digit: int = int(chr(key_code))
            if self._cur_cel == 0:
                if self._day is None or self._should_clear_before_input:
                    self._day = entered_digit
                    self._should_clear_before_input = False
                else:
                    if self._day<10:
                        self._day = entered_digit + int(str(self._day)[0]) * 10
                        self._correct_date()
                        self._cur_cel = 1 # переход на следующую ячейку если ввели двузначное число
                        self._should_clear_before_input = True
                if self._day>0:
                    self._correct_date()

            elif self._cur_cel == 1:
                if self._month is None or self._should_clear_before_input:
                    self._month = entered_digit
                    self._should_clear_before_input = False
                else:
                    if self._month<10:
                        self._month = entered_digit + int(str(self._month)[0]) * 10
                        self._correct_date()
                        self._cur_cel = 2
                        self._should_clear_before_input = True
                if self._month>0:
                    self._correct_date()

            elif self._cur_cel == 2:
                if self._year is None or self._should_clear_before_input:
                    self._year = entered_digit
                    self._year_enter_count = 1
                    self._should_clear_before_input = False
                else:
                    if self._year<10:
                        self._year = entered_digit + int(str(self._year)[0]) * 10
                        self._year_enter_count = 2
                    elif self._year<100:
                        self._year = entered_digit + int(str(self._year)[0:2]) * 10
                        self._year_enter_count = 3
                    elif self._year<1000:
                        self._year = entered_digit + int(str(self._year)[0:3]) * 10
                        self._year_enter_count = 4
                        self._correct_date()
                    else:
                        self._year = entered_digit
                        self._year_enter_count = 1
                self._correct_date()

        elif key_code in [wx.WXK_DELETE, wx.WXK_BACK]:
            if self.GetSelection() == (0,10):
                self._day = None
                self._month = None
                self._year = None
                self._cur_cel = 0
                self._date = None
            else:
                if self._cur_cel == 0:
                    self._day = None
                elif self._cur_cel == 1:
                    self._month = None
                elif self._cur_cel == 2:
                    self._year = None
                self._date = None
            self._correct_date()
            self._should_clear_before_input = True

        elif chr(key_code) in ['.',',','/','\''] or key_code in [wx.WXK_RIGHT, wx.WXK_DOWN]:
            should_execute = True
            if chr(key_code) in ['.',',','/','\'']:
                if self._cur_cel == 0 and self._day is None:
                    should_execute = False
                if self._cur_cel == 1 and self._month is None:
                    should_execute = False
                if self._cur_cel == 2 and self._year is None:
                    should_execute = False
            if should_execute:
                self._should_clear_before_input = True
                self._correct_date()
                self._cur_cel +=1
                if self._cur_cel>2:
                    self._cur_cel = 0
                #if key_code in [wx.WXK_RIGHT, wx.WXK_DOWN]:
                #    self.should_clear_before_input = True
        elif key_code in [wx.WXK_LEFT, wx.WXK_UP]:
            self._correct_date()
            self._should_clear_before_input = True
            self._cur_cel -= 1
            if self._cur_cel<0:
                self._cur_cel = 0
        else:
            #evt.Skip()
            pass
        self._update()
        self._select_item(self._cur_cel)

    def get_value(self):
        return self._date

    def set_value(self, val: datetime.date):
        if val is None or type(val)==datetime.date:
            self._set_date(val)
            return True
        else:
            mlogger.error(f'{self} неверное значение {type(val)} {val}')
            return False




class BasicDateText(wx.TextCtrl, EventPublisher):
    _date: Optional[datetime.date]
    _date_delimiter: str = '.'
    _cur_cel: int = 0

    _day: Optional[int]
    _month: Optional[int]
    _year: Optional[int]

    _year_enter_count: int = 0

    _day_region: wx.Rect
    _month_region: wx.Rect
    _year_region: wx.Rect
    _should_clear_before_input: bool = False



    _cal = None
    _parent: Any
    def __init__(self, parent: Any, id_val: int = wx.ID_ANY, value: Any = '', pos: wx.Point = wx.DefaultPosition, size: wx.Size = wx.DefaultSize, style: int = 0):
        self._parent = parent
        EventPublisher.__init__(self)
        super().__init__(parent,id_val, value, pos, size, style, wx.DefaultValidator, '')
        self.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_event)
        self.Bind(wx.EVT_CHAR, self._on_char)
        self._day = None
        self._month = None
        self._year = None
        self._should_clear_before_input = False
        self._set_date(None)

    _set_date = BasicDatePicker.__dict__["_set_date"]
    #date = BasicDatePicker.__dict__["date"]
    _update = BasicDatePicker.__dict__["_update"]
    _select_item = BasicDatePicker.__dict__["_select_item"]
    _on_mouse_event = BasicDatePicker.__dict__["_on_mouse_event"]
    _on_char = BasicDatePicker.__dict__["_on_char"]
    _correct_date = BasicDatePicker.__dict__["_correct_date"]

    get_value = BasicDatePicker.__dict__["get_value"]
    set_value = BasicDatePicker.__dict__["set_value"]


class BasicTextCtrl(wx.TextCtrl, EventPublisher):
    _parent: Any
    def __init__(self, parent, **kwargs):
        self._parent = parent

        wx.TextCtrl.__init__(self, parent, **kwargs)
        EventPublisher.__init__(self)
        self.Bind(wx.EVT_TEXT, self._on_text_changed)


    def _on_text_changed(self, evt: wx.CommandEvent):
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))
        evt.Skip()

    def set_value(self, value: str):
        if value is None:
            self.SetValue('')
        else:
            if type(value) == str:
                self.SetValue(value)
            else:
                mlogger.error(f'{self} ошибка установки значения {value}, тип не поддерживается')
                return False
        return True

    def get_value(self):
        val = self.GetValue()
        if len(val)==0:
            return None
        return self.GetValue()


class BasicSearch(wx.SearchCtrl, EventPublisher):

    on_text_changed: Optional[Callable[[str], None]]

    def __init__(self, parent: Union[BasicPanel, BasicToolBar]):
        wx.SearchCtrl.__init__(self, parent)
        EventPublisher.__init__(self)
        self.ShowCancelButton(True)
        self.ShowSearchButton(False)
        self.SetDescriptiveText('Поиск')
        self.Bind(wx.EVT_TEXT, self._on_text_changed)
        self.on_text_changed = None

    def _on_text_changed(self, evt: wx.CommandEvent):
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))
        if self.on_text_changed:
            self.on_text_changed(evt.GetString())
        evt.Skip()

    def set_value(self, value: str):
        if value is None:
            self.SetValue('')
        else:
            if type(value) == str:
                self.SetValue(value)
            else:
                mlogger.error(f'{self} ошибка установки значения {value}, тип не поддерживается')
                return False
        return True

    def get_value(self):
        val = self.GetValue()
        if len(val)==0:
            return None
        return self.GetValue()

class BasicCheckBox(wx.CheckBox, EventPublisher):
    _is_3state: bool
    _parent: Any
    def __init__(self, parent, third_state: bool, third_state_user: bool, **kwargs):
        self._parent = parent
        self._is_3state = False
        if 'style' in kwargs.keys():
            style = kwargs['style']
        else:
            style = wx.CHK_2STATE

        if third_state:
            style &= ~wx.CHK_2STATE
            style |= wx.CHK_3STATE
            self._is_3state = True
        if third_state and third_state_user:
            style |= wx.CHK_ALLOW_3RD_STATE_FOR_USER
        kwargs['style'] = style
        wx.CheckBox.__init__(self, parent, **kwargs)
        EventPublisher.__init__(self)
        self.Bind(wx.EVT_CHECKBOX, self._on_checkbox_checked)

    @property
    def third_state(self):
        return self._is_3state

    @third_state.setter
    def third_state(self, value):
        if value:
            style = self.GetWindowStyle()
            style &=~wx.CHK_2STATE
            style |= wx.CHK_3STATE
            style |= wx.CHK_ALLOW_3RD_STATE_FOR_USER
            self.SetWindowStyle(style)
        else:
            style = self.GetWindowStyle()
            style |= wx.CHK_2STATE
            style &= ~wx.CHK_3STATE
            style &= ~wx.CHK_ALLOW_3RD_STATE_FOR_USER
            self.SetWindowStyle(style)

        self._is_3state = value
        self.set_value(False)



    def _on_checkbox_checked(self, evt: wx.CommandEvent):
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))
        evt.Skip()

    def set_value(self, value: Optional[bool]):
        if not (value is None or type(value) == bool):
            mlogger.error(f'{self} Ошибка установки значения {value}, тип не поддерживается')
            return False

        if self._is_3state:
            if value is None:
                self.Set3StateValue(wx.CHK_UNDETERMINED)
            elif value:
                self.Set3StateValue(wx.CHK_CHECKED)
            elif not value:
                self.Set3StateValue(wx.CHK_UNCHECKED)
        else:
            if value:
                self.SetValue(wx.CHK_CHECKED)
            else:
                self.SetValue(wx.CHK_UNCHECKED)

        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))
        return True

    def get_value(self):
        if self._is_3state:
            val = self.Get3StateValue()
            if val == wx.CHK_UNDETERMINED:
                return None
            elif val == wx.CHK_CHECKED:
                return True
            elif val == wx.CHK_UNCHECKED:
                return False
        else:
            val = self.GetValue()
            if val == wx.CHK_CHECKED:
                return True
            elif val == wx.CHK_UNCHECKED:
                return False

        return None

class BasicFileSelect(BasicPanel, EventPublisher):
    _have_doc_img = '32:32:AQAAAQAAAAAAra+vrbCwrK6uq66uq66uq66uq66uq66uq66uq66uq66uq66uq66uq66uq66uq66uq66tq66ura+vqqysAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAra+v////////////////////////////////////////////////////////////////////////6enppaenAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAArK6u////3t/g3+Dh3+Dh3+Dh3+Dh3+Dh3+Dh3+Dh3+Dh3+Dh3+Dh3+Dh3+Dh3+Dh3t/g////o6Wl////5+fnpqmpAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAq66u////4OHi4eLj4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4eLj4OHi////pKen7+/w////5ubmqaysAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAq66u////4eLj4+Tl4+Tl4+Tl4+Tl4+Tl4+Tl4+Tl4+Tl4+Tl4+Tl4+Tl4+Tl4+Tl4eLj////paen+Pn57Ozt////5+fnqq2tAAAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAq66u////4uPk5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm5OXm4uPk////paen////+Pn57+/w////6enpra+vAAAAAQAAAQAAAQAAAQAAAQAAAAAAq66u////4+Tm5ebn5ebn5ebn5ebn5ebn5ebn5ebn5ebn5ebn5ebn5ebn5ebn5ebn4+Tl////ysvLpKenpaenpKenoqWl////ra+vAAAAAQAAAQAAAQAAAQAAAQAAAAAAq66t////5Obn5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ufo5ebn8vHz////////////////////////q66uAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////5efo5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5ufo5ebn5ebo5ebo5ebn5ebn////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////6Ojp6enq6enq6enq6enq6enq6enq6enq6enq6enq6enq6enq6enq6enq6unr6+rs6+rs6enr6enq6Ojp6Ofp////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////6enq6urr6urr6urr6urr6urr6urr6urr6urr6urr6urr6urr6urr6+vt7+309fD99fD97+306+vt6urr6enq////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////6uvr6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs7O3u8fD2/PX/MXsAMXsA/PX/8fD27Ozu6uvr////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////6+zs7O3t7O3t7O3t7O3t7O3t7O3t7O3t7O3t7O3t7O3t7e7v8vD3/vb/NHwAl+EAl+EANHsA/vb/8fD17O3t////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////7O3t7e7u7e7u7e7u7e7u7e7u7e7u7e7u7e7u7e7u7u/w8/H4//j/NHwAmeEAWJwAV5sAl+AAMXoA+PT/7u7w////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////7u/v7u/v7u/v7+/w8PDy8PDy7+/w7u/v7u/v7/Dx9PL6//j/M3sAmOEAXqEAX6IAXaEAl+AAMXoA+fX/7/Dx////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////7/Dw7/Dw8PHy9fP5+vf/+vf/9fP58PHy8PHy9fP6//n/SZIAl98AY6UAZacAcbQAmOEAM3sA//r/9PP47/Dx////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////8fHy8vH0+PX9//v/MHoAMHoA//v/+fb/+fb///v/M3oAlt8Ac7cAaasAaKsAl+AAM3oA//v/9/X98vH08fHy////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////8/L09/X8//z/MnoAld8Ald8AM3oA////////M3oAlt8Abq8Ab68Abq8Al+AAM3oA//z/+Pb+8/P18vLz8vLz////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////9fT3/vn/L3oAld8Ac7MAc7MAl98AOX4AOX4Al98Ac7MAdLQAdLQAlt8AMnoA//3/+ff/9PT28/P08/P08/P0////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////9vX4//r/L3kAld4AeLgAeLgAeLgAl94Al94AeLgAebgAeLgAld4AMnkA//7/+/j/9fX39PT19PT19PT19PT1////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////9vf4+/n/////MXkAld4Af70Afr0AfrwAfrwAfr0Afr0AlN4ASJEA////+/r/9vf49fb29fb29fb29fb29fb2////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////9vf39/j5/Pv/////MXkAlN4Ag8IAg8IAg8IAg8IAlN4AMXkA/////Pr/9/j59vf39vf39vf39vf39vf39vf3////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////+fj4+Pj4+vn6//z/////MXkAlN0AiccAiccAlN0AMXkA//////z/+vn6+Pj4+Pj4+Pj4+Pj4+Pj4+Pj4+fj4////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////+vr6+fn5+fn5+/r7//3/////MXkAlN0AlN0AMXkA//////3/+/r7+fn5+fn5+fn5+fn5+fn5+fn5+fn5+vr6////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t////+/v7+vr6+vr6+vr6/Pv8//7/////LngALngA//////7//Pv8+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+/v7////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t/////Pz8+/v7+/v7+/v7+/v7/fz9//7///////////7//fz9+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7/Pz8////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq62t/////f39/Pz8/Pz8/Pz8/Pz8/Pz8/fz9/v3//v3//fz9/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/f39////q62tAAAAAQAAAQAAAQAAAQAAAQAAAAAAq66u/////////v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+////////q66uAAAAAQAAAQAAAQAAAQAAAQAAAAAArbCw////////////////////////////////////////////////////////////////////////////////////////////rbCwAAAAAQAAAQAAAQAAAQAAAQAAAAAArrCwra+vq66uq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq62tq66ura+vrrCwAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAA:AAAEtP///////////////////////7AEAAAAAAAAAAAAAA3//////////////////////////64DAAAAAAAAAAAAFf///////////////////////////8AEAAAAAAAAAAAW/////////////////////////////+YFAAAAAAAAABb//////////////////////////////+UFAAAAAAAAFv///////////////////////////////+oFAAAAAAAW/////////////////////////////////xAAAAAAABb/////////////////////////////////FgAAAAAAFv////////////////////////////////8WAAAAAAAW/////////////////////////////////xYAAAAAABb/////////////////////////////////FgAAAAAAFv////////////////////////////////8WAAAAAAAW/////////////////////////////////xYAAAAAABb/////////////////////////////////FgAAAAAAFv////////////////////////////////8WAAAAAAAW/////////////////////////////////xYAAAAAABb/////////////////////////////////FgAAAAAAFv////////////////////////////////8WAAAAAAAW/////////////////////////////////xYAAAAAABb/////////////////////////////////FgAAAAAAFv////////////////////////////////8WAAAAAAAW/////////////////////////////////xYAAAAAABb/////////////////////////////////FgAAAAAAFv////////////////////////////////8WAAAAAAAW/////////////////////////////////xYAAAAAABb/////////////////////////////////FgAAAAAAFv////////////////////////////////8WAAAAAAAW/////////////////////////////////xYAAAAAABb/////////////////////////////////FgAAAAAAFvP///////////////////////////////MWAAAAAAAQMUJDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NCMRAAAAAAAAUQFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYQBQAAAA=='
    _have_doc_bmp: wx.Bitmap
    _no_doc_img = '32:32:AQAAAQAAAQAAAAAAiomJiomJAAAAiomJiomJAAAAiomJiomJAAAAiomJiomJAAAAiomJiomJAAAAiomJiomJAAAAiomJAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////////////////////////////////////////////////////////////////////////5ubmiomJAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////zM7Qzc/QztDRztDRztDRztDRztDRztDRztDRztDRztDRztDRztDRzc/QzM7P////iomJ////5OTkAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAAAAA////0NPU0tTV09XW09XW09XW09XW09XW09XW09XW09XW09XW09XW09XW0tTV0NLT////iomJ7e3u////7e3tiomJAAAAAQAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////09TV1dbX1tfY1tfY1tfY1tfY1tfY1tfY1tfY1tfY1tfY1tfY1tfY1dbX09TV////////9fb26urr////4uLiiomJAAAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////1NbX1tjZ19na19na19na19na19na19na19na19na19na19na19na1tjZ1NbX////iomJ////9fb27u7v////5OTkAAAAAQAAAQAAAQAAAQAAAQAAAQAAAAAAQUFB////1tna2Nrc2dvc2dvc2dvc2dvc2dvc2dvc2dvc2dvc2dvc2dvc2dvc2Nvc1tja////xMPDiomJ////iomJiomJ////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////2drb2tvc29zd29zd29zd29zd29zd29zd29zd29zd29zd29zd29zd29zd2drb6err////////////////////////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////29zd3d7f3d7f3d7f3d7f3d7f3d7f3d7f3d7f3d7f3d7f3d7f3d7f3d7f3d3f29zd29zd2tvc2tvc2tvc2drb////AAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAA////3N7f3uDh3uDh3uDh3uDh3uDh3uDh3uDh3uDh3uDh3uDh3uDh3uDh3uDh3uDh3uDh3eDh3eDh3eDh3d/g297f////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////3t/g4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi4OHi3t/g////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////4OHi4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4uPk4OHi////AAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAA////4uPj5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl5OXl4uPj////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////4+bm5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn5efn4+bm////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////5ufo5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5+jp5ufo////AAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAQUFB////6Onp6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6erq6Onp////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////6uzr6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6+zs6uzr////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////6+zu7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u7O3u6+zu////AAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAA////7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v7u/v////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx8PHx////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz8vLz////AAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAA////9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////9fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb29fb2////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////9/f59/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f49/f5////AAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAQUFB////+vr6+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+vr6////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ/////Pz8+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7/Pz8////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ/////f39/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/Pz8/f39////AAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAA////////////////////////////////////////////////////////////////////////////////////////////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAiomJ////////////////////////////////////////////////////////////////////////////////////////////iomJAAAAAQAAAQAAAQAAAQAAAQAAAAAAp6eniomJAAAAiomJiomJNTU1iomJiomJAAAAiomJiomJAAAAiomJiomJNTU1iomJiomJAAAAiomJiomJAAAAiomJiomJAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAA:AAAABv//C///C///C///C///C///C/8GAAAAAAAAAAAAAAb/////////////////////////pv8GAAAAAAAAAAAAEf//////////////////////////rQ8AAAAAAAAAAAARN///////////////////////////p/8GAAAAAAAAAAv/////////////////////////////pv8GAAAAAAAAEf//////////////////////////////rA8AAAAAAAARU////////////////////////////////wYAAAAAAA3/////////////////////////////////EQAAAAAAEf///////////////////////////////zcRAAAAAAARN////////////////////////////////wsAAAAAAAv/////////////////////////////////EQAAAAAAEf///////////////////////////////zcRAAAAAAARN////////////////////////////////wsAAAAAAAv/////////////////////////////////EQAAAAAAEf///////////////////////////////zcRAAAAAAARU////////////////////////////////wsAAAAAAA3/////////////////////////////////EQAAAAAAEf///////////////////////////////zcRAAAAAAARN////////////////////////////////wsAAAAAAAv/////////////////////////////////EQAAAAAAEf///////////////////////////////zcRAAAAAAARN////////////////////////////////wsAAAAAAAv/////////////////////////////////EQAAAAAAEf///////////////////////////////zcRAAAAAAARU////////////////////////////////wsAAAAAAA3/////////////////////////////////EQAAAAAAEf///////////////////////////////zcRAAAAAAARN////////////////////////////////wsAAAAAAAv/////////////////////////////////EQAAAAAAEPX/Tv//Zv//Tv//Tv//Zv//Tv//Tv//SDIRAAAAAAAQMTctNzkvOTctNzctNzkvOTctNzctNzciEQYAAAAAAAUQEAsREQ0REQsREQsREQ0REQsREQsREQYAAAAAAA=='
    _no_doc_bmp: wx.Bitmap


    _parent: Any
    _default_style: int
    _textbox: wx.TextCtrl
    _button: wx.Button
    _checkbox: Optional[wx.CheckBox]
    _drop_file_target: BasicDropFileTarget
    _main_sizer: wx.BoxSizer

    _filename: Optional[str]
    _show_relative_path: bool
    _parent_path: Optional[str]
    _drag_and_drop: bool
    _folder_select: bool
    _button_label: str
    _filename: Optional[str]
    _parent_path: Optional[str]
    _wildcards: str
    _is_third_state: bool

    def __init__(self, parent: Union[BasicPanel, BasicWindow, BasicDialog],show_relative_path:bool, folder_select: bool, can_drag_and_drop: bool):
        BasicPanel.__init__(self, parent)
        EventPublisher.__init__(self)

        self._sizer = wx.GridBagSizer()
        self.SetSizer(self._sizer)

        self._default_style = wx.TE_READONLY #| wx.BORDER_NONE | wx.TE_CENTRE  # глюк wx.WIDGETS следующий, если создать Textbox не с BORDER_NONE,
        self._textbox = wx.TextCtrl(self, style=self._default_style)
        self._button = wx.Button(self)
        self._checkbox = None
        self._drop_file_target = BasicDropFileTarget(self, False)
        self._button.SetDropTarget(self._drop_file_target)

        self._sizer.Add(self._textbox, pos=(0, 0), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL|wx.EXPAND, border=1)
        self._sizer.Add(self._button, pos=(0, 1), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=1)
        self._sizer.AddGrowableCol(0,0)


        self._filename = None
        self._show_relative_path = show_relative_path
        self._parent_path = None

        self._folder_select = folder_select

        self._filename = None
        self._parent_path = None
        self._last_path = None
        self._wildcards = "Файл (*.*)|*.*"
        self._is_third_state = False
        self._button_label = 'Выбрать'


        # то они почему то не устанавливаются в NONE потом, поэтому создаем в начале None, а уж потом устанавилваем

        self._textbox.Bind(wx.EVT_TEXT, self._on_text_changed)
        self._button.Bind(wx.EVT_BUTTON, self._on_openfile_click)

        img_src1: wx.Image = b64_img(self._no_doc_img)
        scaled_image1 = img_src1.Scale(GuiWidgetSettings.file_dialog_bitmap_size.GetWidth(), GuiWidgetSettings.file_dialog_bitmap_size.GetHeight(), wx.IMAGE_QUALITY_BICUBIC)
        self._no_doc_bmp = scaled_image1.ConvertToBitmap()

        img_src2: wx.Image = b64_img(self._have_doc_img)
        scaled_image2 = img_src2.Scale(GuiWidgetSettings.file_dialog_bitmap_size.GetWidth(), GuiWidgetSettings.file_dialog_bitmap_size.GetHeight(), wx.IMAGE_QUALITY_BICUBIC)
        self._have_doc_bmp = scaled_image2.ConvertToBitmap()

        self._button.SetLabel(self._button_label)
        self.drag_and_drop = can_drag_and_drop

    def get_value(self):
        if self._show_relative_path:
            if self._parent_path is not None and self._filename is not None:
                return os.path.relpath(self._filename, self._parent_path)
        return self._filename


    def _set_value(self, filename: Optional[str]):
        self._filename = filename
        if filename is not None:
            if os.path.isabs(filename):
                self._filename = filename
            else:
                if self._parent_path is not None:
                    self._filename = os.path.join(self._parent_path, filename)
            wx.CallAfter(self._textbox.SetValue, self.get_value())
            wx.CallAfter(self._textbox.SetInsertionPointEnd)
        else:
            wx.CallAfter(self._textbox.SetValue, '')
        if self._drag_and_drop:
            self._button.SetLabel('')
            if self._filename:
                if os.path.exists(self._filename):
                    self._button.SetBitmap(self._have_doc_bmp)
                else:
                    self._button.SetBitmap(self._no_doc_bmp)
            else:
                self._button.SetBitmap(self._no_doc_bmp)
        else:
            self._button.SetLabel(self._button_label)


    @property
    def relative_path(self):
        if self._show_relative_path and self._parent_path:
            return self._parent_path
        elif self._show_relative_path and not self._parent_path:
            mlogger.error(f'{self} повреждение структуры: выбраны относительные пути, но относительный путь не задан')
        return None

    @relative_path.setter
    def relative_path(self, val: str):
        if type(val) == str:
            if os.path.exists(val):
                self._show_relative_path = True
                self._parent_path = val
            else:
                mlogger.warning(f'{self} relative_path {val} не существует')
        else:
            self._show_relative_path = False
            self._parent_path = None
        self._set_value(self._filename)


    @property
    def drag_and_drop(self):
        return self._drag_and_drop

    @drag_and_drop.setter
    def drag_and_drop(self, val: bool):
        if type(val) == bool:
            self._drag_and_drop = val
            self._set_value(self._filename)

    @property
    def folder_select(self):
        return self._folder_select

    @folder_select.setter
    def folder_select(self, val:bool):
        if type(val) == bool:
            self._folder_select = val




    def _on_text_changed(self, evt: wx.CommandEvent):
        evt.SetEventObject(self)
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))

    def can_replace_file_dialog_result(self):
        question_dialog =  wx.MessageDialog(self, f"Файл уже выбран. Подтверждаете замену на другой файл?", "Подтверждение", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION).ShowModal()
        if question_dialog == wx.ID_YES:
            return True
        return False

    def _on_openfile_click(self, _evt: wx.CommandEvent):

        if self._filename:
            if not self.can_replace_file_dialog_result():
                return

        default_path = ''
        if self._last_path is not None:
            if os.path.exists(os.path.dirname(self._last_path)):
                default_path = os.path.dirname(self._last_path)
        else:
            if self._parent_path is not None:
                if os.path.exists(self._parent_path):
                    default_path = self._parent_path

        if not self._folder_select:
            file_dialog = wx.FileDialog(self, "Выбрать файл", defaultDir=default_path, wildcard=self._wildcards, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST, name="Выбрать")
        else:
            file_dialog = wx.DirDialog(self, 'Выбрать папку', defaultPath=default_path)
        if file_dialog:
            r = file_dialog.ShowModal()
            if r == wx.ID_OK:
                filename = file_dialog.GetPath()
                self._set_value(filename)
                if os.path.exists(filename):
                    self._last_path = filename
            else:
                self._set_value(None)

    def set_value(self, value: str):
        if not (value is None or type(value) == str):
            mlogger.error(f'{self} Ошибка установки значения {value}, тип не поддерживается')
            return False

        self._set_value(value)
        return True



class BasicControlWithList(EventPublisher, wx.Control):
    _name_value_list: Dict[str, Any] = {}
    _value_name_list: Dict[Any, str] = {}
    _selected_values: Optional[Union[Any, List[Any]]] = None
    _control: Union[wx.ComboBox, wx.ListBox, wx.CheckListBox]
    _used_names: Dict[str, str] = {}
    _names_order: List[str]

    def __init__(self, control: Union[wx.ComboBox, wx.CheckListBox, wx.ListBox]):
        EventPublisher.__init__(self)
        self._control = control
        self._name_value_list = {}
        self._value_name_list = {}
        self._selected_values = None
        self._used_names = {}
        self._names_order = []

    def _add_control_str(self, name: str):
        """функция добавляет в контрол строку"""
        if issubclass(type(self._control), (wx.ComboBox, wx.CheckListBox, wx.ListBox)):
            ctrl: wx.ComboBox = self._control
            ctrl.Append(name)
        else:
            mlogger.error(f'{self} нет обработчика события добавления элемента типа {type(self._control)}')


    def _remove_control_str(self, name: str):
        """функция удаляет из контрола строку"""
        if issubclass(type(self._control), (wx.ComboBox, wx.CheckListBox, wx.ListBox)):
            ctrl: wx.ComboBox = self._control
            sel_index = ctrl.FindString(name, True)
            if sel_index != wx.NOT_FOUND:
                # noinspection PyArgumentList
                ctrl.Remove(sel_index)
            else:
                mlogger.error(f'{self} не найден элемент \"{name}\"')
        else:
            mlogger.error(f'{self} нет обработчика события удаления элемента типа {type(self._control)}')

    def _clear_control_strs(self):
        """функция очищает все строки из контрола"""
        if issubclass(type(self._control), wx.ComboBox):
            ctrl: wx.ComboBox = self._control
            ctrl.Clear()
        elif type(self._control) == BasicCheckListWithFilter:
            #noinspection PyTypeChecker
            ctrl: BasicCheckListWithFilter = self._control
            #noinspection PyProtectedMember
            ctrl._check_list_ctrl.Clear()
        elif type(self._control) == BasicCheckList:
            # noinspection PyTypeChecker
            ctrl: BasicCheckList = self._control
            ctrl.Clear()
        elif type(self._control) == BasicList:
            # noinspection PyTypeChecker
            ctrl: BasicList = self._control
            ctrl.Clear()
        else:
            mlogger.error(f'{self} нет обработчика события очистки элемента типа {type(self._control)}')

    def _select_control_str(self, name: str, selected: bool):
        """функция выполняет отображение выбранного элемента"""
        if issubclass(type(self._control), (wx.ComboBox, wx.CheckListBox, wx.ListBox)):
            sel_index = self._control.FindString(name, True)
            if sel_index != wx.NOT_FOUND:
                if issubclass(type(self._control), wx.CheckListBox):
                    ctrl: wx.CheckListBox = self._control
                    ctrl.Check(sel_index, selected)
                elif issubclass(type(self._control), (wx.ComboBox, wx.ListBox)):
                    ctrl: wx.ComboBox = self._control
                    if issubclass(type(self._control), wx.ComboBox):
                        if selected:
                            ctrl.Select(sel_index)
                    elif issubclass(type(self._control), wx.ListBox):
                        ctrl: wx.ListBox = self._control
                        if ctrl.IsSelected(sel_index) and not selected:
                            ctrl.Select(sel_index)
                        elif not ctrl.IsSelected(sel_index) and selected:
                            ctrl.Select(sel_index)
            else:
                mlogger.error(f'{self} не найден элемент \"{name}\"')
        else:
            mlogger.error(f'{self} нет обработчика события выбора элемента типа {type(self._control)}')


    def _clear_control_selection(self):
        if issubclass(type(self._control), (wx.ComboBox, wx.CheckListBox, wx.ListBox)):
            if issubclass(type(self._control), wx.CheckListBox):
                ctrl: wx.CheckListBox = self._control
                for i in range(ctrl.GetCount()):
                    ctrl.Check(i, False)
            elif issubclass(type(self._control), (wx.ComboBox, wx.ListBox)):
                ctrl: wx.ComboBox = self._control
                if issubclass(type(self._control), wx.ComboBox):
                    ctrl.Select(-1)
                elif issubclass(type(self._control), wx.ListBox):
                    ctrl: wx.ListBox = self._control
                    ctrl.Select(wx.NOT_FOUND)
        else:
            mlogger.error(f'{self} нет обработчика события выбора элемента типа {type(self._control)}')

    def _on_control_str_selected(self, name: Optional[str], selected: bool):
        """функция вызывается если пользователь выбрал элемент"""
        if name is not None:
            if name not in self._name_value_list.keys():
                mlogger.error(f'{self} on_control_str_selected не найден элемент \"{name}\"')
                return

        if issubclass(type(self._control), (wx.ComboBox, wx.CheckListBox, wx.ListBox)):
            if issubclass(type(self._control), wx.ComboBox):
                if selected:
                    if name is not None:
                        self._selected_values = self._name_value_list[name]
                    else:
                        self._selected_values = None
                else:
                    self._selected_values = None
            elif issubclass(type(self._control), (wx.CheckListBox, wx.ListBox)):
                if self._selected_values is None:
                    self._selected_values = []
                else:
                    if type(self._selected_values) != list:
                        old_val = self._selected_values
                        self._selected_values = []
                        self._selected_values.append(old_val)
                if name is not None:
                    item = self._name_value_list[name]
                else:
                    item = None
                if selected:
                    if item is not None:
                        if item not in self._selected_values:
                            self._selected_values.append(item)
                    else:
                        self._selected_values.clear()
                    #else:
                    #    mlogger.error(f'{self} элемент \"{name}\" уже помечен как выбранный')
                else:
                    if item is not None:
                        if item in self._selected_values:
                            self._selected_values.remove(item)
                    else:
                        self._selected_values.clear()
                    #else:
                    #    mlogger.error(f'{self} элемент \"{name}\" уже удален как не выбранный')

            self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))

        else:
            mlogger.error(f'{self} нет обработчика события выбора от пользователя элемента типа {type(self._control)}')

    def set_available_values(self, avail_list: List[Tuple[str, Any]]):
        self._name_value_list.clear()
        self._value_name_list.clear()
        self._used_names.clear()
        self._names_order.clear()
        self._clear_control_strs()
        self._selected_values = None
        for (item_name, item_val) in avail_list:
            if item_val not in self._value_name_list.keys():
                new_name = item_name
                if item_name in self._name_value_list.keys():
                    i = 1
                    while item_name+f'({i})' in self._name_value_list.keys():
                        i+=1
                    new_name = item_name+f'({i})'
                self._value_name_list[item_val] = new_name
                self._name_value_list[new_name] = item_val
                self._used_names[new_name.lower()] = new_name
                self._add_control_str(new_name)
                self._names_order.append(new_name)
            else:
                mlogger.error(f'{self} значение {item_name} {item_val} не может быть добавлено')

    def get_available_values(self):
        answ = []
        for name in self._names_order:
            answ.append(self._name_value_list[name])
        return answ


    def set_value(self, val: Any):
        if val == self._selected_values:
            return True
        if issubclass(type(self._control), wx.ComboBox):
            if val is None:
                self._selected_values = None
            elif type(val) == list:
                self._selected_values = None
            else:
                if val in self._value_name_list.keys():
                    self._selected_values = val
                else:
                    mlogger.error(f'{self} значение {type(val)} не найдено в _value_name_list')
                    return False

        elif issubclass(type(self._control), (wx.CheckListBox, wx.ListBox)):
            if val is None:
                self._selected_values = None
            elif type(val) == list:
                if type(self._selected_values) != list:
                    self._selected_values = []
                for v in val:
                    self._selected_values.append(v)
            else:
                self._selected_values = [val]
                #mlogger.error(f'{self} значение {type(val)} не является списком {val}')
                #self._selected_values = None
        else:
            mlogger.error(f'{self}  set_value нет обработчика типа {type(self._control)}')
            return False
        self._clear_control_selection()

        if self._selected_values is not None and type(self._selected_values)==list:
            for name in self._names_order:
                if self._name_value_list.keys():
                    obj_item = self._name_value_list[name]
                    if obj_item in self._selected_values:
                        self._select_control_str(name, True)
                    else:
                        self._select_control_str(name, False)
                else:
                    mlogger.error(f'{self} значение для {name} не найдено в _name_value_list')
        elif self._selected_values is not None and type(self._selected_values) != list:
            self._select_control_str(self._value_name_list[self._selected_values], True)
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))
        return True

    def get_value(self):
        if self._selected_values is None:
            return None
        if issubclass(type(self._control), wx.ComboBox):
            return self._selected_values
        elif issubclass(type(self._control), (wx.CheckListBox, wx.ListBox)):
            if type(self._selected_values) == list:
                answ = []
                for name in self._names_order:
                    obj_item = self._name_value_list[name]
                    if obj_item in self._selected_values:
                        answ.append(obj_item)
            else:
                answ = [self._selected_values]
                mlogger.error(f'{self} выбранные значения имеют неверный тип {type(self._selected_values)}')
            return answ
        else:
            mlogger.error(f'{self} нет обработчика получения значения типа {type(self._control)}')
        return self._selected_values

    def get_object(self, name: str)->Any:
        if name in self._name_value_list.keys():
            return self._name_value_list[name]
        return None

    def get_name(self, obj: Any)->str:
        if obj in self._value_name_list.keys():
            return self._value_name_list[obj]



class BasicCombobox(wx.ComboBox,BasicControlWithList):
    # внимание, загрузка 3000 значений занимает 29 секунд или по 1 секунде на каждые 100 значений
    _parent: Any
    _sorted: bool
    _current_text: str
    _read_only: bool
    def __init__(self, parent, **kwargs):
        self._parent = parent
        if 'style' in kwargs.keys():
            style = kwargs['style']
        else:
            style = 0
        style |= wx.TAB_TRAVERSAL
        if style & wx.CB_SORT == wx.CB_SORT:
            self._sorted = True
        else:
            self._sorted = False
        if style & wx.CB_READONLY == wx.CB_READONLY:
            self._read_only = True
        else:
            self._read_only = False
        if 'pos' not in kwargs.keys():
            kwargs['pos']= wx.DefaultPosition
        if 'size' not in kwargs.keys():
            kwargs['size']= wx.DefaultSize

        wx.ComboBox.__init__(self, parent, wx.ID_ANY, **kwargs)  # | wx.CB_DROPDOWN, **par)
        BasicControlWithList.__init__(self, self)
        self.Bind(wx.EVT_COMBOBOX, self._on_value_changed)
        self.Bind(wx.EVT_CHAR, self._evt_char)
        self._current_text = ''


    def _on_value_changed(self, evt: wx.CommandEvent):
        selected_str = evt.GetString()
        if evt.GetInt()==-1:
            self._on_control_str_selected(None, True)
        else:
            self._on_control_str_selected(selected_str, True)
        evt.Skip()

    def _evt_char(self, event: wx.KeyEvent):
        keycode = event.GetKeyCode()
        if 32<=keycode<=255 and keycode!=127:
            self._current_text += chr(event.GetUnicodeKey())
        else:
            self._current_text = ''
            if keycode == wx.WXK_DELETE:
                self.SetSelection(-1)
                self._current_text = ''
                cmd_evt = wx.CommandEvent(wx.wxEVT_COMMAND_COMBOBOX_SELECTED, self.GetId())
                cmd_evt.SetInt(-1)
                cmd_evt.SetString('')
                wx.PostEvent(self, cmd_evt)
            event.Skip()
            return
        search_text = self._current_text.lower()
        found = False
        for tmp_str in self._used_names:
            if tmp_str.startswith(search_text):
                self.set_value(self._name_value_list[self._used_names[tmp_str]])
                if not self._read_only:
                    self.SetInsertionPoint(len(self._current_text))
                    self.SetTextSelection(len(self._current_text), len(tmp_str))
                found = True
                break
        if not found:
            self._current_text = ''



class BasicCheckList(wx.CheckListBox, BasicControlWithList):
    _colors: Dict[str, Optional[wx.Colour]] = {}
    _parent: Any
    _current_text: str

    def __init__(self, parent, **kwargs):
        self._parent = parent
        wx.CheckListBox.__init__(self, parent, **kwargs)
        BasicControlWithList.__init__(self, self)
        self.item_checked_callback = None
        self._colors = {}
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_CHAR, self._evt_char)
        self._current_text = ''
        self.Bind(wx.EVT_CHECKLISTBOX, self._on_item_checked)

    def _on_item_checked(self, evt:wx.CommandEvent):
        item_name = self.GetString(evt.GetInt())
        # evt.GetInt() will contain the index of the item that was checked or unchecked.
        # wx.CommandEvent.IsChecked is not valid!!! Use wx.CheckListBox.IsChecked instead. ^^
        is_checked = self.IsChecked(evt.GetInt())
        self._on_control_str_selected(item_name, is_checked)
        if self.item_checked_callback is not None:
            #on_checklistbox_value_changed(self, _item_name: str, _item_object: Any, _is_checked: bool):
            self.item_checked_callback(item_name, self._name_value_list[item_name], is_checked)

    def _evt_char(self, event: wx.KeyEvent):
        keycode = event.GetKeyCode()
        if 32<=keycode<=255 and keycode!=127:
            self._current_text += chr(event.GetUnicodeKey())
        else:
            self._current_text = ''
            event.Skip()
            return
        search_text = self._current_text.lower()
        found = False
        for tmp_str in self._used_names:
            if tmp_str.startswith(search_text):
                sel_index = self.FindString(tmp_str)
                if sel_index != wx.NOT_FOUND:
                    self.SetFirstItem(sel_index)
                found = True
                break
        if not found:
            self._current_text = ''

    def _on_key_down(self, evt: wx.KeyEvent):
        evt.Skip()
        if evt.GetKeyCode() not in [wx.WXK_DOWN, wx.WXK_UP]:
            return
        sel_items = self.GetSelections()
        if len(sel_items)!=1:
            return
        if self.GetCount() != len(self._names_order):
            return
        sel_index = self.GetSelection()
        other_index = sel_index
        if evt.ControlDown() and evt.GetKeyCode() == wx.WXK_UP:
            if sel_index<=0:
                return
            other_index = sel_index -1
        elif evt.ControlDown() and evt.GetKeyCode() == wx.WXK_DOWN:
            if sel_index>=self.GetCount()-1:
                return
            other_index = sel_index + 1


        frozen = self.IsFrozen()
        if not frozen:
            self.Freeze()

        sel_name = self.GetString(sel_index)
        other_name = self.GetString(other_index)

        l_i1 = self._names_order.index(sel_name)
        l_i2 = self._names_order.index(other_name)
        ch1 = self.IsChecked(l_i1)
        ch2 = self.IsChecked(l_i2)

        self._names_order[l_i1], self._names_order[l_i2] = self._names_order[l_i2], self._names_order[l_i1]
        self.SetString(l_i1, other_name)
        self.SetString(l_i2, sel_name)
        self.Check(l_i1, ch2)
        self.Check(l_i2, ch1)
        if sel_name in self._colors.keys():
            self.set_color(sel_name, self._colors[sel_name])
        else:
            self.set_color(sel_name, None)
        if other_name in self._colors.keys():
            self.set_color(other_name, self._colors[other_name])
        else:
            self.set_color(other_name, None)

        if not frozen:
            self.Thaw()

    def set_color(self, name:str, color: Optional[wx.Colour]):
        if name in self._names_order:
            self._colors[name] = color
            val_index = self.FindString(name, True)
            if val_index != wx.NOT_FOUND:
                if color is None:
                    color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_LISTBOX)
                self.SetItemBackgroundColour(val_index, color)
                if __debug__:
                    mlogger.debug(f'{self} выбор элемента {name}')
        else:
            mlogger.error(f'{self} функция установки цвета для элемента не нашла элемент {name}')

    def get_names(self):
        return list(self._names_order)

    def show_names(self, names: List[str]):
        self.Clear()
        for name in self._names_order:
            if name in names:
                cur_index = self.Append(name)
                if self._selected_values:
                    if self._name_value_list[name] in self._selected_values:
                        self.Check(cur_index,True)
                if name in self._colors.keys():
                    self.set_color(name, self._colors[name])

    def set_names_order(self, names_list: List[str]):
        frozen = self.IsFrozen()
        if not frozen:
            self.Freeze()
        #for name in names_list:
        #    if name not in self._names_order:
        #        return False
        #if len(names_list) != len(self._names_order):
        #    return False
        if len(names_list)==len(self._names_order):
            self._names_order.clear()

            for i, name in enumerate(names_list):
                if name in self._name_value_list.keys():
                    self._names_order.append(name)
                    self.SetString(i, name)
                    if self._selected_values:
                        if self._name_value_list[name] in self._selected_values:
                            self.Check(i, True)
                        else:
                            self.Check(i, False)
                    else:
                        self.Check(i, False)
                    if name in self._colors.keys():
                        self.set_color(name, self._colors[name])
        if not frozen:
            self.Thaw()

    def get_visible_names(self):
        names = []
        for i in range(self.GetCount()):
            names.append(self.GetString(i))
        return names

    def get_checked_names(self):
        names = []
        for i in range(self.GetCount()):
            if self.IsChecked(i):
                names.append(self.GetString(i))
        return names



class BasicList(wx.ListBox, BasicControlWithList):
    _parent: Any

    _current_text: str
    def __init__(self, parent,  **kwargs):
        self._parent = parent
        self._colors = {}
        wx.ListBox.__init__(self, parent, **kwargs)
        BasicControlWithList.__init__(self, self)
        self.evt_listbox_callback = None
        self._values = {}
        self.Bind(wx.EVT_LISTBOX, self._on_item_clicked)
        self.Bind(wx.EVT_CHAR, self._evt_char)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self._current_text = ''

    def _on_item_clicked(self, _evt:wx.CommandEvent):
        selected_indexes = self.GetSelections()
        if not self._selected_values:
            self._selected_values = []
        else:
            self._selected_values.clear()
        for sel_index in selected_indexes:
            sel_name = self.GetString(sel_index)
            sel_obj = self._name_value_list[sel_name]
            if sel_obj not in self._selected_values:
                self._on_control_str_selected(sel_name, True)


    def _evt_char(self, event: wx.KeyEvent):
        keycode = event.GetKeyCode()
        if 32<=keycode<=255 and keycode!=127:
            self._current_text += chr(event.GetUnicodeKey())
        else:
            self._current_text = ''
            event.Skip()
            return
        search_text = self._current_text.lower()
        found = False
        for tmp_str in self._used_names:
            if tmp_str.startswith(search_text):
                sel_index = self.FindString(tmp_str)
                if sel_index != wx.NOT_FOUND:
                    self.SetFirstItem(sel_index)
                found = True
                break
        if not found:
            self._current_text = ''

    def _on_key_down(self, evt: wx.KeyEvent):
        evt.Skip()
        if evt.GetKeyCode() not in [wx.WXK_DOWN, wx.WXK_UP]:
            return

        sel_items = self.GetSelections()
        if len(sel_items)!=1:
            return
        if self.GetWindowStyleFlag() & wx.LB_MULTIPLE != wx.LB_MULTIPLE:
            sel_index = self.GetSelection()
        else:
            sel_index = sel_items[0]
        other_index = sel_index

        if evt.ControlDown() and evt.GetKeyCode() == wx.WXK_UP:
            if sel_index<=0:
                return
            other_index = sel_index -1
        elif evt.ControlDown() and evt.GetKeyCode() == wx.WXK_DOWN:
            if sel_index>=self.GetCount()-1:
                return
            other_index = sel_index + 1
        if sel_index == other_index:
            return

        frozen = self.IsFrozen()
        if not frozen:
            self.Freeze()

        sel_name = self.GetString(sel_index)
        other_name = self.GetString(other_index)

        l_i1 = self._names_order.index(sel_name)
        l_i2 = self._names_order.index(other_name)

        self._names_order[l_i1], self._names_order[l_i2] = self._names_order[l_i2], self._names_order[l_i1]
        self.SetString(l_i1, other_name)
        self.SetString(l_i2, sel_name)
        if sel_name in self._colors.keys():
            self.set_color(sel_name, self._colors[sel_name])
        else:
            self.set_color(sel_name, None)
        if other_name in self._colors.keys():
            self.set_color(other_name, self._colors[other_name])
        else:
            self.set_color(other_name, None)

        if self.GetWindowStyleFlag() & wx.LB_MULTIPLE == wx.LB_MULTIPLE:
            self.SetSelection(wx.NOT_FOUND)
            self.SetSelection(other_index)

        if not frozen:
            self.Thaw()

    def set_color(self, name:str, color: Optional[wx.Colour]):
        if name in self._names_order:
            self._colors[name] = color
            val_index = self.FindString(name, True)
            if val_index != wx.NOT_FOUND:
                if color is None:
                    color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_LISTBOX)
                self.SetItemBackgroundColour(val_index, color)
                if __debug__:
                    mlogger.debug(f'{self} выбор элемента {name}')
        else:
            mlogger.error(f'{self} функция установки цвета для элемента не нашла элемент {name}')


class BasicTwinTextCtrl(BasicPanel, EventPublisher):
    _first_ctrl: BasicTextCtrl
    _second_ctrl: BasicTextCtrl
    _l: EventSubscriber
    def __init__(self, parent):
        EventPublisher.__init__(self)
        BasicPanel.__init__(self, parent)
        self._l = EventSubscriber()
        self._l.on_notify = self.on_notify
        self._first_ctrl = BasicTextCtrl(self)
        self._first_ctrl.register_listener(self._l)
        self._second_ctrl = BasicTextCtrl(self)
        self._second_ctrl.register_listener(self._l)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self._first_ctrl, 0, wx.ALL | wx.EXPAND, 2)
        sizer.Add(self._second_ctrl, 0, wx.ALL| wx.EXPAND, 2)
        self.SetSizer(sizer)
        self.Layout()


    def on_notify(self, _event_type: EventType, _event_object: EventObject):
        #EventSubscriber.on_notify(self, event_type, event_object)
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))

    def get_value(self):
        val1 = self._first_ctrl.GetValue()
        val2 = self._second_ctrl.GetValue()
        if not val1:
            val1 = None
        if not val2:
            val2 = None
        return val1, val2


    def set_value(self, value: Tuple[str, str]):
        if value:
            if type(value) in [tuple, list] and len(value)>=2:
                val1 = value[0]
                val2 = value[1]
                if val1:
                    self._first_ctrl.SetValue(val1)
                if val2:
                    self._second_ctrl.SetValue(val2)
                return True
            else:
                mlogger.error(f'{self} ошибка установки значения {value}')
        return False



class BasicCheckListWithFilter(BasicPanel, BasicControlWithList):
    _check_list_ctrl: BasicCheckList
    _filter_text_ctrl: Union[wx.TextCtrl, wx.SearchCtrl]
    _selected_count_ctrl: wx.StaticText
    _check_visible_btn: wx.Button
    _uncheck_visible_btn: wx.Button
    _invert_checked_btn: wx.Button
    _show_checked_ctrl: wx.CheckBox
    _event_listener: EventSubscriber
    _parent: Any

    def __init__(self, parent, **kwargs):
        self._parent = parent
        EventPublisher.__init__(self)
        # BORDER_THEME - подходящее или BORDER_DOUBLE

        if 'style' in kwargs.keys():
            kwargs['style'] = kwargs['style'] | wx.BORDER_DOUBLE
        else:
            kwargs['style'] =  wx.BORDER_DOUBLE
        BasicPanel.__init__(self, parent, **kwargs)

        self._event_listener = EventSubscriber()
        self._event_listener.on_notify = self._on_notify_event_listener

        self._filter_text_ctrl = wx.SearchCtrl(self) #wx.TextCtrl(self)
        self._filter_text_ctrl.ShowCancelButton(True)
        self._filter_text_ctrl.SetDescriptiveText('Поиск')
        #self._filter_text_ctrl.SetHint('Допускается использовать символы маски *,?')
        #self._filter_text_ctrl.SHowS
        self._filter_text_ctrl.Bind(wx.EVT_TEXT, self._on_filter_text_changed)
        self._check_list_ctrl = BasicCheckList(self, **kwargs)
        self._check_list_ctrl.register_listener(self._event_listener)


        self._check_list_ctrl.register_listener(self._event_listener)
        self._check_visible_btn = wx.Button(self, label="Пометить")
        self._check_visible_btn.Bind(wx.EVT_BUTTON, self._on_check_visible_btn_click)
        self._uncheck_visible_btn = wx.Button(self, label="Очистить")
        self._uncheck_visible_btn.Bind(wx.EVT_BUTTON, self._on_uncheck_visible_btn_click)
        self._invert_checked_btn = wx.Button(self, label="Инвертировать")
        self._invert_checked_btn.Bind(wx.EVT_BUTTON, self._on_invert_checked_btn_click)
        self._show_checked_ctrl = wx.CheckBox(self)
        self._show_checked_ctrl.SetLabelText('Показ.выбр.')
        self._show_checked_ctrl.Bind(wx.EVT_CHECKBOX, self._on_show_checked_ctrl)

        sizer = wx.BoxSizer(wx.VERTICAL)
        h_sizer1 = wx.BoxSizer(wx.HORIZONTAL)
        #filter_label = wx.StaticText(self, label="Фильтр:")
        #h_sizer1.Add(filter_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 1)
        h_sizer1.Add(self._filter_text_ctrl, 1, wx.ALL | wx.EXPAND, 1)

        sizer.Add(h_sizer1, 0, wx.EXPAND | wx.ALL, 1)
        self._selected_count_ctrl = wx.StaticText(self)
        sizer.Add(self._selected_count_ctrl, 0, wx.EXPAND | wx.ALL, 1)
        sizer.Add(self._check_list_ctrl, 1, wx.EXPAND | wx.ALL, 1)
        h_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(h_sizer, 0, wx.EXPAND | wx.ALL, 1)
        h_sizer.Add(self._check_visible_btn, 0, wx.ALL, 1)
        h_sizer.Add(self._uncheck_visible_btn, 0, wx.ALL, 1)
        h_sizer.Add(self._invert_checked_btn, 0, wx.ALL, 1)
        h_sizer.Add(self._show_checked_ctrl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 1)

        self.SetSizer(sizer)
        self._on_notify_event_listener(EventType.ITEM_CHANGED, EventObject(self._check_list_ctrl))

    def _on_notify_event_listener(self, _event_type: EventType, _event_object: EventObject):
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))
        len1 = self._check_list_ctrl.get_value()
        len2 = self._check_list_ctrl.get_available_values()
        if len1 is None:
            len1 = 0
        else:
            len1= len(len1)
        if len2 is None:
            len2 = 0
        else:
            len2 = len(len2)
        self._selected_count_ctrl.SetLabel(f'Выбрано {len1} из {len2}')

    def _on_filter_text_changed(self, evt: wx.CommandEvent):
        old_len = len(self._check_list_ctrl.get_visible_names())
        names = self._check_list_ctrl.get_names()

        filter_text = evt.GetString().lower()
        f_val = re.escape(filter_text)
        f_val = f_val.replace('\\*', '.*?')
        f_val = f_val.replace('\\?', '.')
        flag = re.IGNORECASE
        f_val = f_val + '.*?'
        for name in list(names):
            result = re.match(f'^{f_val}$', name, flags=flag)
            if not result:
                names.remove(name)
        self._check_list_ctrl.show_names(names)
        new_len = len(self._check_list_ctrl.get_visible_names())
        if old_len != new_len:
            self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))


    def _on_check_visible_btn_click(self, _evt: wx.CommandEvent):
        for i in range(self._check_list_ctrl.GetCount()):
            self._check_list_ctrl.Check(i, True)
            cmd_evt = wx.CommandEvent(wx.wxEVT_CHECKLISTBOX, self.GetId())
            cmd_evt.SetInt(i)
            wx.PostEvent(self._check_list_ctrl, cmd_evt)

    def _on_uncheck_visible_btn_click(self, _evt: wx.CommandEvent):
        for i in range(self._check_list_ctrl.GetCount()):
            self._check_list_ctrl.Check(i, False)
            cmd_evt = wx.CommandEvent(wx.wxEVT_CHECKLISTBOX, self.GetId())
            cmd_evt.SetInt(i)
            wx.PostEvent(self._check_list_ctrl, cmd_evt)

    def _on_invert_checked_btn_click(self, _evt: wx.CommandEvent):
        for i in range(self._check_list_ctrl.GetCount()):
            checked = self._check_list_ctrl.IsChecked(i)
            self._check_list_ctrl.Check(i, not checked)
            cmd_evt = wx.CommandEvent(wx.wxEVT_CHECKLISTBOX, self.GetId())
            cmd_evt.SetInt(i)
            wx.PostEvent(self._check_list_ctrl, cmd_evt)


    def enable_control(self, enable: bool):
        self._check_list_ctrl.Enable(enable)
        self._check_visible_btn.Enable(enable)
        self._uncheck_visible_btn.Enable(enable)
        self._invert_checked_btn.Enable(enable)

    def is_control_enabled(self):
        return self._check_list_ctrl.IsEnabled()

    def _on_show_checked_ctrl(self, evt: wx.CommandEvent):
        chk_box: wx.CheckBox = evt.GetEventObject()
        if chk_box.IsChecked():
            self._check_list_ctrl.show_names(self._check_list_ctrl.get_checked_names())
        else:
            self._check_list_ctrl.show_names(self._check_list_ctrl.get_names())

    def set_color(self, name: str, color: Optional[wx.Colour]):
        self._check_list_ctrl.set_color(name, color)

    def get_value(self):
        return self._check_list_ctrl.get_value()

    def get_visible_value(self):
        names = self._check_list_ctrl.get_visible_names()
        answ = []
        for name in names:
            obj = self._check_list_ctrl.get_object(name)
            if obj not in answ:
                answ.append(obj)
        return answ

    def set_value(self, val: Any):

        return self._check_list_ctrl.set_value(val)


    def get_available_values(self):
        return self._check_list_ctrl.get_available_values()

    def set_available_values(self, avail_list: List[Tuple[str, Any]]):
        self._check_list_ctrl.set_available_values(avail_list)
        self._on_notify_event_listener(EventType.ITEM_CHANGED, EventObject(self._check_list_ctrl))




class PropertiesPanel(BasicPanel, EventPublisher):
    parent: Union[BasicPanel, BasicWindow, BasicDialog]
    ini_config: Optional[configparser.ConfigParser]

    file_dialog_attributes: Dict[str, Tuple]
    property_names: List[str]
    _parent: Any
    def __init__(self, parent: Union[BasicPanel, BasicWindow, BasicDialog], ini_config: Optional[configparser.ConfigParser]):
        self._parent = parent
        EventPublisher.__init__(self)
        self.file_dialog_attributes = {}
        self.property_names = []
        self.parent = parent
        self.data_changed_callback = None
        self.ini_config = ini_config
        BasicPanel.__init__(self, parent)
        self.pg: wxpg.PropertyGrid = wxpg.PropertyGrid(self, style=wxpg.PG_TOOLBAR)  # wxpg.PG_AUTO_SORT
        self.pg.Bind(wxpg.EVT_PG_CHANGED, self.on_prop_grid_change)
        #self.pg.Bind(wxpg.EVT_PG_CHANGING, self.on_prop_grid_changing)
        #self.pg.Bind(wxpg.EVT_PG_LABEL_EDIT_BEGIN, self.on_prop_grid_text_begin_change)
        #self.pg.Bind(wxpg.EVT_PG_LABEL_EDIT_ENDING, self.on_prop_grid_text_end_change)
        self.pg.Bind(wxpg.EVT_PG_SELECTED, self.on_item_selected)
        self.pg.DedicateKey(wx.WXK_RETURN)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.main_sizer)
        self.main_sizer.Add(self.pg, 1, wx.EXPAND | wx.ALL,0)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)
        self.Layout()
        self.pg.ResetColumnSizes(False)

    def load_splitter_pos(self):
        if self.ini_config is not None:
            if self.ini_config.has_section('properties_panel') and self.ini_config.has_option('properties_panel', 'split_pos'):
                splitter_pos = int(self.ini_config['properties_panel']['split_pos'])
                self.pg.SetSplitterPosition(splitter_pos, 0)

    def on_destroy(self, evt: wx.WindowDestroyEvent):

        if evt.GetEventObject() == self:

            self.pg = None

            self.Unbind(wxpg.EVT_PG_CHANGED)
            self.Unbind(wxpg.EVT_PG_SELECTED)
            #pg.Destroy()

        mlogger.debug(f'Destroyed {self}')


    def set_splitter_left(self):
        self.pg.SetSplitterLeft()


    def save_state(self):
        if self.ini_config is not None:
            if not self.ini_config.has_section('properties_panel'):
                self.ini_config.add_section('properties_panel')
            self.ini_config['properties_panel']['split_pos'] = str(self.pg.GetSplitterPosition(0))

    def on_prop_grid_change(self, event: wxpg.PropertyGridEvent):

        if self.pg is not None:
            if self.data_changed_callback is not None:
                self.data_changed_callback()
            event.Skip()

    def _store_filedialog_attributes(self):
        for name in self.property_names:
            prop = self.pg.GetPropertyByName(name)
            if type(prop) == wxpg.FileProperty:
                show_relative = prop.GetAttribute(wxpg.PG_FILE_SHOW_RELATIVE_PATH)
                show_fullpath = prop.GetAttribute(wxpg.PG_FILE_SHOW_FULL_PATH)
                self.file_dialog_attributes[name] = (show_relative, show_fullpath,)

    def _restore_filedialog_attributes(self):
        for name in self.property_names:
            prop: wxpg.FileProperty = self.pg.GetPropertyByName(name)
            if type(prop) == wxpg.FileProperty and name in self.file_dialog_attributes.keys():
                prop.SetAttribute(wxpg.PG_FILE_SHOW_RELATIVE_PATH, self.file_dialog_attributes[name][0])
                prop.SetAttribute(wxpg.PG_FILE_SHOW_FULL_PATH, self.file_dialog_attributes[name][1])

    @staticmethod
    def on_item_selected(event: wxpg.PropertyGridEvent):
        #prop: wxpg.FileProperty = event.GetProperty()
        #if type(prop) == wxpg.FileProperty:
        #    self._restore_filedialog_attributes()
        #    self._store_filedialog_attributes()
        #    self.set_filedialog_show_filename(prop.GetName(), True, False)
        event.Skip()


    def add_category(self, category_name: str):
        self.pg.Append(wxpg.PropertyCategory(category_name))
        #if self.ini_config.has_option(self.window_name, 'pg_width'):
        #    splitter_pos = int(self.ini_config[self.window_name]['pg_width'])
        #    self.pg.SetSplitterPosition(splitter_pos, 0)
        self.pg.SetSplitterLeft()

    def add_property(self, property_name: str, property_label: str, property_type: Union[Type,wxpg.EditorDialogProperty], property_value: Any):
        prop = None
        if property_type == str:
            prop = wxpg.StringProperty(property_label, property_name)
        elif property_type == int:
            prop = wxpg.IntProperty(property_label, property_name)
        elif property_type == float:
            prop = wxpg.FloatProperty(property_label, property_name,)
        elif property_type == bool:
            prop = wxpg.BoolProperty(property_label, property_name)
        elif property_type == datetime.date:
            prop = wxpg.DateProperty(property_label, property_name)
        elif property_type == wxpg.DirProperty:
            prop = wxpg.DirProperty(property_label, property_name, "")
        elif property_type == wxpg.FileProperty:
            prop = wxpg.FileProperty(property_label, property_name, "")
        elif property_type == wx.Colour:
            prop = wxpg.ColourProperty(property_label, property_name)
        elif property_type == wx.Font:
            prop = wxpg.FontProperty(property_label, property_name)
        elif property_type == wx.Brush:
            #br: BrushStyle = property_value
            data = [('Сплошное',wx.BRUSHSTYLE_SOLID),
                    ('Диагональ вправо', wx.BRUSHSTYLE_BDIAGONAL_HATCH),
                    ('Диагональ влево', wx.BRUSHSTYLE_FDIAGONAL_HATCH),
                    ('Пересечение', wx.BRUSHSTYLE_CROSSDIAG_HATCH)]

            labels = [d[0] for d in data]
            values = [d[1] for d in data]
            if property_value is None:
                property_value = -1
            prop = wxpg.EnumProperty(property_label, property_name, labels, values, property_value)
            if property_value == -1:
                prop.SetValueToUnspecified()
            #if property_value is not None:
            #    prop.SetValue(gui_drawer.wx_resources.get_wx_font(property_value))
            #else:
            #    prop.SetValueToUnspecified()
        elif property_type == TextAlign:
            #br: TextAlign = property_value
            data = [('Влево',wx.ALIGN_LEFT),
                    ('Вправо', wx.ALIGN_RIGHT),
                    ('Вниз', wx.ALIGN_TOP),
                    ('Вверх', wx.ALIGN_BOTTOM),
                    ('По центру', wx.ALIGN_CENTER),
                    ('Влево, центр по вертикали', wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL),
                    ('Вправо, центр по вертикали', wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL),
                    ('Вверх, центр по горизонтали', wx.ALIGN_TOP | wx.ALIGN_CENTER_HORIZONTAL),
                    ('Вниз, центр по горизонтали', wx.ALIGN_BOTTOM | wx.ALIGN_CENTER_HORIZONTAL)]
            labels = [d[0] for d in data]
            values = [d[1] for d in data]
            if property_value is None:
                property_value = -1
            prop = wxpg.EnumProperty(property_label, property_name, labels, values, property_value)
            if property_value == -1:
                prop.SetValueToUnspecified()
            #if property_value is not None:
            #    prop.SetValue(gui_drawer.wx_resources.get_wx_font(property_value))
            #else:
            #    prop.SetValueToUnspecified()
        else:
            mlogger.error(f'{self} Неизвестный тип данных {property_type}')
        if prop is not None:
            prop.SetAutoUnspecified(True)
            self.property_names.append(property_name)
            self.pg.Append(prop)
            if property_type == bool:
                self.pg.SetPropertyAttribute(property_name, wxpg.PG_BOOL_USE_CHECKBOX, True)
            elif property_type == wxpg.FileProperty:
                if property_value is not None and type(property_value) is str:
                    # noinspection PyTypeChecker
                    split_path = os.path.split(property_value)
                    if len(split_path)>1:
                        self.pg.SetPropertyAttribute(property_name, wxpg.PG_FILE_INITIAL_PATH, split_path[0])
            elif property_type == datetime.date:
                self.pg.SetPropertyAttribute(property_name, wxpg.PG_DATE_PICKER_STYLE, wx.adv.DP_DROPDOWN)
            self.set_property_value(property_name, property_value)
        #self.pg.CenterSplitter(True)

    def set_property_value(self, property_name: str, property_value: Any):
        prop: wxpg.EditorDialogProperty = self.pg.GetPropertyByName(property_name)
        if prop is None:
            return
        simple_set = False
        if type(prop) == wxpg.StringProperty:
            simple_set = True
        elif type(prop) == wxpg.IntProperty:
            simple_set = True
        elif type(prop) == wxpg.FloatProperty:
            simple_set = True
        elif type(prop) == wxpg.BoolProperty:
            simple_set = True
        elif type(prop) == wxpg.DateProperty:
            if type(property_value) == datetime.date:
                property_value = _date_to_wxdate(property_value)
            simple_set = True
        elif type(prop) == wxpg.DirProperty:
            if type(property_value) == str:
                if os.path.exists(property_value):
                    prop.SetValue(property_value)
                #else:
                #    prop.SetValue(None)
            #else:
            #    property_value = ''
        elif type(prop) == wxpg.FileProperty:
            prop.SetValue('')
            if type(property_value) == str:
                if os.path.exists(os.path.split(property_value)[0]):
                    self.set_filedialog_initial_dir(property_name,os.path.split(property_value)[0])
                    prop.SetValue(property_value)

                #else:
                #    prop.SetValue(None)
            #else:
            #    prop.SetValue(None)

        elif type(prop) == wxpg.ColourProperty:
            if type(property_value) == wx.Colour:
                property_value = property_value.val
            else:
                property_value = None
            simple_set = True
        elif type(prop) == wxpg.FontProperty:
            if type(property_value) == wx.Font:
                property_value = property_value.val
            else:
                property_value = None
            simple_set = True
        elif type(property_value) == wx.Brush and type(prop) == wxpg.EnumProperty:
            property_value = property_value.val
            if property_value <0:
                property_value = None
            simple_set = True
        elif type(property_value) == TextAlign and type(prop) == wxpg.EnumProperty:
            property_value = property_value.val
            if property_value < 0:
                property_value = None
            simple_set = True


        if simple_set:
            if property_value is not None:
                prop.SetValue(property_value)
            else:
                prop.SetValueToUnspecified()

    def set_filedialog_initial_dir(self, property_name: str, dir_name: str):
        prop: wxpg.EditorDialogProperty = self.pg.GetPropertyByName(property_name)
        if prop is not None and type(prop) == wxpg.FileProperty:
            self.pg.SetPropertyAttribute(property_name, wxpg.PG_FILE_INITIAL_PATH, dir_name)

    def set_filedialog_title(self, property_name: str, title: str):
        prop: wxpg.EditorDialogProperty = self.pg.GetPropertyByName(property_name)
        if prop is not None and type(prop) == wxpg.FileProperty:
            self.pg.SetPropertyAttribute(property_name, wxpg.PG_DIALOG_TITLE, title)


    def set_filedialog_extension(self, property_name: str, file_ext: str):
        prop: wxpg.EditorDialogProperty = self.pg.GetPropertyByName(property_name)
        if prop is not None and type(prop) == wxpg.FileProperty:
            self.pg.SetPropertyAttribute(property_name, wxpg.PG_FILE_WILDCARD, file_ext)

    def set_filedialog_style(self, property_name: str, dialog_style: int = wx.FD_OPEN):
        prop: wxpg.EditorDialogProperty = self.pg.GetPropertyByName(property_name)
        if prop is not None and type(prop) == wxpg.FileProperty:
            self.pg.SetPropertyAttribute(property_name, wxpg.PG_FILE_DIALOG_STYLE, dialog_style)


    def set_filedialog_show_filename(self, property_name: str, show_full_path:bool, show_relative_path: bool):
        prop: wxpg.EditorDialogProperty = self.pg.GetPropertyByName(property_name)
        if prop is not None and type(prop) == wxpg.FileProperty:
            self.pg.SetPropertyAttribute(property_name, wxpg.PG_FILE_SHOW_FULL_PATH, show_full_path)
            self.pg.SetPropertyAttribute(property_name, wxpg.PG_FILE_SHOW_RELATIVE_PATH, show_relative_path)

    def set_dirdialog_title(self, property_name: str, title: str):
        prop: wxpg.EditorDialogProperty = self.pg.GetPropertyByName(property_name)
        if prop is not None and type(prop) == wxpg.DirProperty:
            self.pg.SetPropertyAttribute(property_name, wxpg.PG_DIALOG_TITLE, title)

    def get_property_value(self, property_name: str)->Any:
        prop: wxpg.PGProperty = self.pg.GetPropertyByName(property_name)
        val = None
        if prop is not None:
            val = self.pg.GetPropertyValue(property_name)

        if prop.IsValueUnspecified():
            return None
        if type(prop) == wxpg.StringProperty:
            return val
        elif type(prop) == wxpg.IntProperty:
            return val
        elif type(prop) == wxpg.FloatProperty:
            return val
        elif type(prop) == wxpg.BoolProperty:
            return val
        elif type(prop) == wxpg.DateProperty:
            return _wxdate_to_date(val)
        elif type(prop) == wxpg.FontProperty:
            return val
        elif type(prop) == wxpg.ColourProperty:
            return val
        elif type(prop) == wxpg.DirProperty:
            return val
        elif type(prop) == wxpg.FileProperty:
            return self.get_filedialog_filename(property_name)
        else:
            mlogger.error(f'{self} Неизвестный тип данных {val}')
        return None

    def get_filedialog_filename(self, property_name: str):
        prop: wxpg.FileProperty = self.pg.GetPropertyByName(property_name)
        file_name = prop.GetFileName()
        #init_dir = prop.GetAttribute(wxpg.PG_FILE_INITIAL_PATH)
        #if file_name not in [None,'']:
        #    if not os.path.isabs(file_name):
        #        return os.path.normpath(os.path.abspath(os.path.join(init_dir, file_name)))
        return file_name


    def set_data_changed_callback(self, c: Callable):
        self.data_changed_callback = c

class BasicPropertyGrid(wxpg.PropertyGrid):
    _parent: Any
    def __init__(self, parent):
        self._parent = parent
        wxpg.PropertyGrid.__init__(self, parent, style=wxpg.PG_SPLITTER_AUTO_CENTER | wxpg.PG_TOOLBAR)
        self.Bind(wxpg.EVT_PG_CHANGED, self.on_prop_grid_change)
        #self.AddActionTrigger(wxpg.PG_ACTION_NEXT_PROPERTY, wx.WXK_DOWN)
        #self.AddActionTrigger(wxpg.PG_ACTION_EDIT, wx.WXK_DOWN)
        self.DedicateKey(wx.WXK_DOWN)
        #self.AddActionTrigger(wxpg.PG_ACTION_PREV_PROPERTY, wx.WXK_UP)
        self.DedicateKey(wx.WXK_UP)


    def add_category(self, category_name: str):
        self.Append(wxpg.PropertyCategory(category_name))
        self.SetSplitterLeft()

    def add_property(self, property_name: str, property_label: str, property_type: Union[Type,wxpg.EditorDialogProperty], property_value: Any):
        prop = None
        if property_type == str:
            prop = wxpg.StringProperty(property_label, property_name)
            if property_value is not None:
                prop.SetValue(property_value)
            else:
                prop.SetValueToUnspecified()
        elif property_type == int:
            prop = wxpg.IntProperty(property_label, property_name)
            if property_value is not None:
                prop.SetValue(property_value)
            else:
                prop.SetValueToUnspecified()
        elif property_type == float:
            prop = wxpg.FloatProperty(property_label, property_name,)
            if property_value is not None:
                prop.SetValue(property_value)
            else:
                prop.SetValueToUnspecified()
        elif property_type == bool:
            prop = wxpg.BoolProperty(property_label, property_name)
            if property_value is not None:
                prop.SetValue(property_value)
            else:
                prop.SetValueToUnspecified()
        elif property_type == datetime.date:
            prop = wxpg.DateProperty(property_label, property_name)
            if property_value is not None:
                prop.SetValue(property_value)
            else:
                prop.SetValueToUnspecified()
        elif property_type == wxpg.DirProperty:
            prop = wxpg.DirProperty(property_label, property_name, "")
            if property_value is not None:
                if os.path.exists(property_value):
                    prop.SetValue(property_value)
            #else:
            #    prop.SetValueToUnspecified()
        elif property_type == wxpg.FileProperty:
            prop = wxpg.FileProperty(property_label, property_name, "")
            if property_value is not None:
                if os.path.exists(property_value):
                    prop.SetValue(property_value)
            #else:
            #    prop.SetValueToUnspecified()
        elif property_type == wx.Colour:
            prop = wxpg.ColourProperty(property_label, property_name)
            if property_value is not None:
                prop.SetValue(property_value)
            else:
                prop.SetValueToUnspecified()
        elif property_type == wx.Font:
            prop = wxpg.FontProperty(property_label, property_name)
            prop.SetValue(wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT))
            if property_value is not None:
                prop.SetValue(property_value)
        elif property_type == BrushStyle:
            #br: BrushStyle = property_value
            data = [(' ', BrushStyle.EMPTY),
                    ('Сплошное', BrushStyle.SOLID),
                    ('Диагональ вправо', BrushStyle.RIGHT_DIAGONAL),
                    ('Диагональ влево', BrushStyle.LEFT_DIAGONAL),
                    ('Пересечение диагоналей', BrushStyle.CROSSDIAG),
                    ('Горизонталь', BrushStyle.HORIZONTAL),
                    ('Вертикаль', BrushStyle.VERTICAL),
                    ('Клетка', BrushStyle.SQUARE)]

            labels = [d[0] for d in data]
            values = [d[1] for d in data]
            if property_value is None:
                property_value = -1
            prop = wxpg.EnumProperty(property_label, property_name, labels, values, property_value)
            if property_value == -1:
                prop.SetValueToUnspecified()
            #if property_value is not None:
            #    prop.SetValue(gui_drawer.wx_resources.get_wx_font(property_value))
            #else:
            #    prop.SetValueToUnspecified()
        elif property_type == TextAlign:
            #br: TextAlign = property_value
            data = [('Влево', TextAlign.ALIGN_LEFT),
                    ('Вправо', TextAlign.ALIGN_RIGHT),
                    ('Вниз', TextAlign.ALIGN_TOP),
                    ('Вверх', TextAlign.ALIGN_BOTTOM),
                    ('По центру', TextAlign.ALIGN_CENTER),
                    ('Влево, центр по вертикали', TextAlign.ALIGN_CENTER_LEFT),
                    ('Вправо, центр по вертикали', TextAlign.ALIGN_CENTER_RIGHT),
                    ('Вверх, центр по горизонтали', TextAlign.ALIGN_CENTER_TOP),
                    ('Вниз, центр по горизонтали', TextAlign.ALIGN_CENTER_BOTTOM)]
            labels = [d[0] for d in data]
            values = [d[1] for d in data]
            if property_value is None:
                property_value = -1
            prop = wxpg.EnumProperty(property_label, property_name, labels, values, property_value)
            if property_value == -1:
                prop.SetValueToUnspecified()
            #if property_value is not None:
            #    prop.SetValue(gui_drawer.wx_resources.get_wx_font(property_value))
            #else:
            #    prop.SetValueToUnspecified()
        else:
            mlogger.error(f'{self} Неизвестный тип данных {property_type}')
        if prop is not None:
            prop.SetAutoUnspecified(True)
            self.Append(prop)
            if property_type == bool:
                self.SetPropertyAttribute(property_name, wxpg.PG_BOOL_USE_CHECKBOX, True)
            elif property_type == wxpg.FileProperty:
                if property_value is not None and type(property_value) is str:
                    # noinspection PyTypeChecker
                    split_path = os.path.split(property_value)
                    if len(split_path)>1:
                        self.SetPropertyAttribute(property_name, wxpg.PG_FILE_INITIAL_PATH, split_path[0])
            elif property_type == datetime.date:
                self.SetPropertyAttribute(property_name, wxpg.PG_DATE_PICKER_STYLE, wx.adv.DP_DROPDOWN)
        #self.pg.CenterSplitter()
        self.FitColumns() # !!!какая-то внутренняя ошибка компонента, обязательно требуется вызывать эту функцию дважды, тогда работает автоопределение положения!!!
        self.FitColumns() # !!!какая-то внутренняя ошибка компонента, обязательно требуется вызывать эту функцию дважды, тогда работает автоопределение положения!!!
        #self.pg.Update()
        #self.pg.CenterSplitter()

        #self.pg.Update()
        #self.pg.SetSplitterLeft()
        #if self.ini_config.has_option(self.window_name, 'pg_width'):
        #    splitter_pos = int(self.ini_config[self.window_name]['pg_width'])
        #    self.pg.SetSplitterPosition(splitter_pos, 0)

    def get_properties_count(self):
        i = 0
        for _prop in self.Properties:
            i+=1
        return i


    def get_items_height(self):
        return self.get_properties_count()*self.GetRowHeight()

    def get_property_value(self, property_name: str)->Any:
        val = self.GetPropertyValue(property_name)
        prop: wxpg.PGProperty = self.GetProperty(property_name)
        if prop.IsValueUnspecified():
            return None
        if type(val) == str:
            return val
        elif type(val) == int:
            return val
        elif type(val) == float:
            return val
        elif type(val) == bool:
            return val
        elif type(val) == wx.DateTime:
            return _wxdate_to_date(val)
        elif type(val) == wx.Font:
            return val
        elif type(val) == wx.Colour:
            return val
        else:
            mlogger.error(f'{self} Неизвестный тип данных {val}')
        return None


    def set_splitter_position(self, value: int):
        self.SetSplitterPosition(value)

    def on_prop_grid_change(self, event: wxpg.PropertyGridEvent):

        event.Skip()

class PropertiesWindow(BasicDialog):
    prop_grid: BasicPropertyGrid
    _parent: Any
    def __init__(self, parent: Union[wx.Frame, wx.grid.Grid, BasicPanel, wx.Dialog], window_name: str, bitmap: Union[wx.Bitmap, str, None], ini_config: Optional[configparser.ConfigParser], default_size: wx.Size):
        self._parent = parent
        BasicDialog.__init__(self, parent, window_name, bitmap, wx.DefaultPosition, wx.DefaultSize, ini_config, True)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self.prop_grid = BasicPropertyGrid(self)
        #self.pg: wxpg.PropertyGrid = wxpg.PropertyGrid(self, style=wxpg.PG_SPLITTER_AUTO_CENTER | wxpg.PG_TOOLBAR)  # wxpg.PG_AUTO_SORT
        #self.pg.Bind(wxpg.EVT_PG_CHANGED, self.on_prop_grid_change)
        #self.pg.AddActionTrigger(wxpg.PG_ACTION_NEXT_PROPERTY, wx.WXK_RETURN)
        #self.pg.AddActionTrigger(wxpg.PG_ACTION_EDIT, wx.WXK_RETURN)

        #self.pg.AddActionTrigger(wxpg.PG_ACTION_EDIT, wx.WXK_RETURN)

        #self.Bind(wx.EVT_NAVIGATION_KEY, self.on_navigation)
        self.main_sizer.Add(self.prop_grid, 1,  wx.EXPAND | wx.ALL, 0)
        btnsizer = wx.StdDialogButtonSizer()
        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)
        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()
        self.main_sizer.Add(btnsizer, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)
        self.SetSizer(self.main_sizer)

        try:
            size_w = default_size.GetWidth()
            size_h = default_size.GetHeight()
            screen_size = wx.DisplaySize()
            pos_x = int((screen_size[0] - size_w) / 2)
            pos_y = int((screen_size[1] - size_h) / 2)
            if self.ini_file is not None:

                if self.ini_file.has_section(self.window_name):

                    if self.ini_file.has_option(self.window_name, 'sizew'):
                        size_w = int(self.ini_file[self.window_name]['sizew'])
                    if self.ini_file.has_option(self.window_name, 'sizeh'):
                        size_h = int(self.ini_file[self.window_name]['sizeh'])

                    if self.ini_file.has_option(self.window_name, 'posx'):
                        pos_x = int(self.ini_file[self.window_name]['posx'])

                    if self.ini_file.has_option(self.window_name, 'posy'):
                        pos_y = int(self.ini_file[self.window_name]['posy'])
                    #if self.ini_config.has_option(self.window_name,'pg_width'):
                    #    splitter_pos = int(self.ini_config[self.window_name]['pg_width'])
                    #    self.pg.SetSplitterPosition(splitter_pos,0)

            self.SetPosition(wx.Point(pos_x, pos_y))
            self.SetSize(wx.Size(size_w, size_h))
        except Exception as ex:
            mlogger.error(f"{self} PropertiesWindow Ошибка загрузки файла конфигурации {window_name} {ex}")

        self.Bind(wx.EVT_ACTIVATE, self.on_lost_focus)
        if __debug__:
            mlogger.debug(f'{self} PropertiesWindow создание: {window_name}')

    #def on_navigation(self, event: wx.NavigationKeyEvent):
    #    #sel = self.pg.GetSelection()
    #    event.Skip()

    def _on_close(self, evt: wx.CloseEvent):
        evt.Skip()
        pos_x = self.GetPosition()[0]
        pos_y = self.GetPosition()[1]
        size_w = self.GetSize()[0]
        size_h = self.GetSize()[1]
        if self.ini_file is not None:
            if not self.ini_file.has_section(self.window_name):
                self.ini_file.add_section(self.window_name)
            self.ini_file[self.window_name]['posx'] = str(pos_x)
            self.ini_file[self.window_name]['posy'] = str(pos_y)
            self.ini_file[self.window_name]['sizew'] = str(size_w)
            self.ini_file[self.window_name]['sizeh'] = str(size_h)
            #splitter_pos = self.pg.GetSplitterPosition(0)
            #self.ini_config[self.window_name]['pg_width'] = str(splitter_pos)


    def on_lost_focus(self, event: wx.ActivateEvent):
        if event.GetEventObject() == self:
            event.Skip()

        if __debug__:
            mlogger.debug(f'{self} PropertiesWindow сохранение: {self.GetTitle()}')

    def add_button(self, _param_label: str, button_label: str, bitmap: Optional[wx.Bitmap], on_button_callback: Callable):
        bitmap_button = wx.Button(self, label=button_label)
        if bitmap is not None:
            bitmap_button.SetBitmap(bitmap)
        bitmap_button.Bind(wx.EVT_BUTTON, on_button_callback)
        self.main_sizer.Insert(1, bitmap_button, flag=wx.ALL, border=5)
        self.main_sizer.Layout()

def message_box(parent:Union[wx.Frame, wx.Panel, wx.ScrolledCanvas, wx.Dialog, wx.App, wx.TreeCtrl], title: str, msg_str: str, msg_type: int, message_details_str: str=''):

    if not message_details_str:
        dial:wx.MessageDialog = wx.MessageDialog(parent, msg_str, title, wx.OK | wx.STAY_ON_TOP | wx.CENTRE | msg_type)
    else:
        dial: wx.RichMessageDialog = wx.RichMessageDialog(parent, msg_str, title, wx.OK | wx.STAY_ON_TOP | wx.CENTRE | msg_type)
        dial.ShowDetailedText(message_details_str)
    dial.ShowModal()
    parent.Raise()
    parent.Update()
    parent.Refresh()



class BasicThirdStateControl(BasicPanel, EventPublisher, EventSubscriber):
    _checkbox: Optional[wx.CheckBox]
    available_types: List[Any] = [ BasicTextCtrl,
                                    BasicDatePicker,
                                    BasicDateText,
                                    BasicCombobox,
                                    BasicCheckList,
                                    BasicCheckListWithFilter,
                                    BasicFileSelect,
                                    BasicCheckBox,
                                    BasicList]

    _control: Optional[Union[BasicDatePicker, BasicDateText, BasicCombobox, BasicFileSelect, BasicCheckBox, BasicTextCtrl, BasicCheckList, BasicCheckListWithFilter, BasicList]]
    _sizer: wx.BoxSizer

    _backup_value: Any
    third_state_value_str = '<не изменять>'
    _is_third_state: bool
    _replacement_text: Optional[wx.StaticText]
    _parent: 'InputOutputPanel'

    def __init__(self, parent: 'InputOutputPanel', item_class: Type, is_third_state: bool, **kwargs):
        BasicPanel.__init__(self, parent)
        self._parent = parent
        EventPublisher.__init__(self)
        EventSubscriber.__init__(self)
        self._is_third_state = is_third_state
        self._replacement_text = None # wx.StaticText(self, label=self.third_state_value)

        self._sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._control: Optional[Union[BasicDatePicker, BasicDateText, BasicCombobox, BasicCheckList, BasicFileSelect]] = None

        need_add_checkbox: bool = True
        if item_class in self.__class__.available_types:
            if item_class == BasicCheckBox:
                need_add_checkbox = False
                self._control = BasicCheckBox(self, True, True)
            else:
                self._control = item_class(self, **kwargs)
            if self._control:
                self._control.register_listener(self)
            else:
                mlogger.error(f'{self} ошибка создания {item_class}')
        else:
            mlogger.error(f'{self} ошибка создания {item_class} не найден в available_types')
        self._backup_value = None

        self.SetSizer(self._sizer)
        if need_add_checkbox:
            self._replacement_text = wx.StaticText(self, label=self.third_state_value_str, style=wx.BORDER_SIMPLE | wx.ALIGN_CENTRE_HORIZONTAL | wx.ALIGN_CENTER_VERTICAL)
            self._replacement_text.Bind(wx.EVT_LEFT_DOWN, self._on_label_click)
            self._sizer.Add(self._replacement_text, 1, wx.EXPAND, 0)
        if self._control:
            self._sizer.Add(self._control, 1, wx.ALL | wx.EXPAND, 1)  # | wx.ALIGN_CENTER_VERTICAL
            self._control.Fit()
            self._control.Layout()
            #if self._replacement_text:
            #    self._replacement_text.SetMinSize(self._control.GetSize())


        if need_add_checkbox:
            self._checkbox = wx.CheckBox(self)
            self._sizer.Add(self._checkbox, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 1)
            self._checkbox.Bind(wx.EVT_CHECKBOX, self._on_checkbox_changed)

        else:
            self._checkbox = None
        #self.is_third_state = is_third_state

        self.Update()
        self.is_third_state = is_third_state

    def _on_label_click(self, evt: wx.MouseEvent):
        if evt.LeftDown():
            self.set_value(None)

    def get_value(self):
        if type(self._control) == BasicTextCtrl:
            ctrl: BasicTextCtrl = self._control
            if self._is_third_state:
                return BasicTextCtrl
            else:
                return ctrl.get_value()
        elif type(self._control) in [BasicDateText, BasicDatePicker]:
            ctrl: Union[BasicDateText, BasicDatePicker] = self._control
            if self._is_third_state:
                return BasicDateText
            else:
                return ctrl.get_value()
        elif type(self._control) in [BasicCombobox]:
            ctrl: Union[BasicCombobox] = self._control
            if self._is_third_state:
                return BasicCombobox
            else:
                return ctrl.get_value()
        elif type(self._control) in [BasicCheckList, BasicCheckListWithFilter]:
            ctrl: Union[BasicCheckList, BasicCheckListWithFilter] = self._control
            if self._is_third_state:
                return BasicCheckList
            else:
                return ctrl.get_value()
        elif type(self._control) == BasicFileSelect:
            ctrl: BasicFileSelect = self._control
            if self._is_third_state:
                return BasicFileSelect
            else:
                return ctrl.get_value()
        elif type(self._control) == BasicCheckBox:
            ctrl: BasicCheckBox = self._control
            val = ctrl.get_value()
            if val is None:
                return BasicCheckBox
            else:
                return ctrl.get_value()
        elif type(self._control) == BasicList:

            ctrl: BasicList = self._control
            val = ctrl.get_value()
            if val is None:
                return BasicList
            else:
                return ctrl.get_value()

        else:
            mlogger.error(f'{self} get_value нет обработчика для {type(self._control)}')

    def set_value(self, value: Any):
        self._backup_value = value
        if type(self._control) == BasicTextCtrl:
            ctrl: BasicTextCtrl = self._control
            if value == BasicTextCtrl:
                self.is_third_state = True
            else:
                self.is_third_state = False
                return ctrl.set_value(value)
        elif type(self._control) in [BasicDateText, BasicDatePicker]:
            ctrl: Union[BasicDateText, BasicDatePicker] = self._control
            if value in [BasicDateText, BasicDatePicker]:
                self.is_third_state = True
            else:
                self.is_third_state = False
                return ctrl.set_value(value)
        elif type(self._control) in [BasicCombobox]:
            ctrl: BasicCombobox = self._control
            if value == BasicCombobox:
                self.is_third_state = True
            else:
                self.is_third_state = False
                return ctrl.set_value(value)
        elif type(self._control) in [BasicCheckList, BasicCheckListWithFilter]:
            ctrl: Union[BasicCheckList, BasicCheckListWithFilter] = self._control
            if value in [BasicCheckList, BasicCheckListWithFilter]:
                self.is_third_state = True
            else:
                self.is_third_state = False
                return ctrl.set_value(value)
        elif type(self._control) == BasicFileSelect:
            ctrl: BasicFileSelect = self._control
            if value == BasicFileSelect:
                self.is_third_state = True
            else:
                self.is_third_state = False
                return ctrl.set_value(value)
        elif type(self._control) == BasicCheckBox:
            if value is None:
                value = False
            ctrl: BasicCheckBox = self._control
            if value == BasicCheckBox:
                self.is_third_state = True
            else:
                self.is_third_state = False
                return ctrl.set_value(value)
        elif type(self._control) == BasicList:
            ctrl: BasicList = self._control
            if value == BasicList:
                self.is_third_state = True
            else:
                self.is_third_state = False
                return ctrl.set_value(value)
        else:
            self._backup_value = None
            mlogger.error(f'{self} set value нет обработчика для {type(self._control)}')
        return False

    def set_available_values(self, values: List[Tuple[str, Any]]):
        if type(self._control) == BasicTextCtrl:
            pass
        elif type(self._control) in [BasicDateText, BasicDatePicker]:
            pass
        elif type(self._control) in [BasicCombobox]:
            ctrl: BasicCombobox = self._control
            ctrl.set_available_values(values)
        elif type(self._control) in [BasicCheckList, BasicCheckListWithFilter, BasicList]:
            ctrl: Union[BasicCheckList, BasicCheckListWithFilter] = self._control
            ctrl.set_available_values(values)
        elif type(self._control) == BasicFileSelect:
            pass
        elif type(self._control) == BasicCheckBox:
            pass
        else:
            mlogger.error(f'{self} set_available_values нет обработчика для {type(self._control)}')

    def get_min_size(self):
        return self._sizer.GetMinSize()

    @property
    def third_state(self):
        if self._checkbox:
            return self._checkbox.IsShown()
        else:
            ctrl: BasicCheckBox
            ctrl = self._control
            return ctrl.third_state

    @third_state.setter
    def third_state(self, value):
        if self._checkbox:
            self._checkbox.Show(value)
            if not value and self.is_third_state:
                self.is_third_state = False
        else:
            ctrl: BasicCheckBox
            ctrl = self._control
            ctrl.third_state = value


    @property
    def is_third_state(self):
        return self._is_third_state


    #def update_third_state(self):
    #    self.is_third_state = self._is_third_state

    @is_third_state.setter
    def is_third_state(self, val: bool):
        if type(val) == bool:
            if self._checkbox:
                frozen = self.IsFrozen()
                if not frozen:
                    self.Freeze()
                #self._replacement_text.SetMinSize(self._control.GetSize())
                self._is_third_state = val
                if val:
                    #self._backup_value = self._control.get_value()
                    self._replacement_text.Show()
                    self._control.Hide()
                else:
                    #if self._replacement_text:
                    #    self._replacement_text.Hide()
                    self._replacement_text.Hide()
                    self._control.Show()
                    #if self._b
                    #self._control.set_value(self._backup_value)

                self._checkbox.SetValue(val)
                self._control.Enable(not val)
                self._sizer.Layout()
                if hasattr(self._parent, 'on_sub_ctrl_change_size'):
                    self._parent.on_sub_ctrl_change_size()
                if not frozen:
                    self.Thaw()
            else:
                ctrl: BasicCheckBox
                ctrl = self._control
                if val:
                    ctrl.set_value(None)
                else:
                    ctrl.set_value(self._backup_value)
                if hasattr(self._parent, 'on_sub_ctrl_change_size'):
                    self._parent.on_sub_ctrl_change_size()



    def get_control(self):
        return self._control

    def set_color(self, name: str, color: Optional[wx.Colour]):
        self._control.set_color(name, color)

    def _on_checkbox_changed(self, evt: Optional[wx.CommandEvent]):
        chk_box = self._checkbox.GetValue()
        if chk_box == wx.CHK_CHECKED:
            self.is_third_state = True
        elif chk_box == wx.CHK_UNCHECKED:
            self.is_third_state = False
        self.notify_listeners(EventType.ITEM_CHANGED, EventObject(self))
        if evt:
            evt.Skip()
        self._parent.SendSizeEventToParent()

    def on_notify(self, event_type: EventType, event_object: EventObject):
        EventSubscriber.on_notify(self, event_type, event_object)
        if (self._checkbox and not self._is_third_state) or not self._checkbox:
            self.notify_listeners(event_type, EventObject(self))

class InputOutputPanel(wx.lib.scrolledpanel.ScrolledPanel, BasicPanel):
    _controls: Dict[str, Union[wx.Control]]
    _control_types: Dict[str, Type]
    _control_labels: Dict[str, wx.StaticText]
    _control_sizer: wx.GridBagSizer
    _control_with_third_state: List[str]
    _notify_changes: bool

    sizeable: bool
    scrollable: bool
    _parent: Union[wx.Dialog, wx.SplitterWindow, wx.Notebook, wx.Panel, 'InputBox']

    _event_listener: EventSubscriber
    property_value_changed_callback: Optional[Callable[['InputOutputPanel', str], None]]
    key_enter_pressed_callback: Optional[Callable[['InputOutputPanel'], None]]

    size_changed_callback: Optional[Callable[[],None]]
    @property
    def parent(self)->Union[wx.Dialog, wx.SplitterWindow, wx.Notebook, wx.Panel, 'InputBox']:
        return self._parent


    def __init__(self, parent: Union[wx.Dialog, wx.SplitterWindow, wx.Notebook, wx.Panel], sizeable: bool, scrollable: bool, border:int=1):
        """создание панели ввода данных - больше всего времени тратится на создание огромног количества объектов"""
        self._parent = parent
        self._event_listener = EventSubscriber()
        self._event_listener.on_notify = self._on_property_changed_notify
        self._controls = {}
        self._control_types = {}
        self._control_labels = {}
        self._notify_changes = True

        #self.main_sizer = wx.BoxSizer(wx.VERTICAL)

        self._control_sizer = wx.GridBagSizer(0, 0)
        self._control_sizer.SetEmptyCellSize((0, 0))

        self.sizeable = sizeable
        self.scrollable = scrollable
        self._control_with_third_state = []

        if scrollable:
            #size = wx.DisplaySize()
            wx.lib.scrolledpanel.ScrolledPanel.__init__(self, parent, style=wx.WANTS_CHARS)
        else:
            BasicPanel.__init__(self, parent, style=wx.WANTS_CHARS)
            #self.panel = wx.Panel(self)

        #self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        #self.main_sizer.Add(self._control_sizer, 1, wx.EXPAND | wx.ALL, border)
        self._border = border
        self.Bind(wx.EVT_CHAR_HOOK, self._on_enter_key_pressed)
        self.Bind(wx.EVT_SIZE, self._on_resize)
        #self._info_ctrl = BasicInfoBar(self, False)
        #self.main_sizer.Add(self._info_ctrl, 0, wx.EXPAND | wx.ALL, 0)
        #self.main_sizer.Add(self._control_sizer,1, wx.EXPAND| wx.ALL,0)
        #self.SetSizer(self.main_sizer)
        self.SetSizer(self._control_sizer)
        if scrollable:
            self.SetupScrolling()
        self.key_enter_pressed_callback = None
        self.property_value_changed_callback = None
        self.size_changed_callback = None



    # region События, при изменении значения

    def _on_resize(self, evt:wx.SizeEvent):
        #self._control_sizer.Layout()
        #self.SendSizeEventToParent()
        #self.Update()
        self.Refresh()
        evt.Skip()

    def on_sub_ctrl_change_size(self):
        self._control_sizer.Layout()
        #self.main_sizer.Layout()
        if self.size_changed_callback:
            self.size_changed_callback()
            #used for update!! SendSizeEvent - should call, else wouldnt change
            #sizer.Layout()
            #frm.Layout()
            #frm.Update()
            #frm.SendSizeEvent()

        #self.Unbind(wx.EVT_SIZE)
        #self.GetParent().Layout()
        #self.GetParent().Update()
        #self.Bind(wx.EVT_SIZE, self._on_resize)

    def _on_property_changed_notify(self, event_type: EventType, event_object: EventObject):
        if event_type == EventType.ITEM_CHANGED:
            prop_name = None
            for key, value in self._controls.items():
                if value == event_object.obj:
                    prop_name = key
                    break
            if prop_name is None:
                mlogger.error(f'{self} событие изменения для элемента {event_object.obj}. Не найден объект в self._controls')
                return
            if self._notify_changes:
                if self.property_value_changed_callback:
                    self.property_value_changed_callback(self, prop_name)


    def _on_enter_key_pressed(self, evt: wx.KeyEvent):
        evt.Skip()
        if evt.GetKeyCode() == wx.WXK_RETURN:
            if self.key_enter_pressed_callback:
                self.key_enter_pressed_callback(self)

    #endregion

    def _property_builder(self, prop_type: Optional[Type], third_state: bool, **kwargs):
        # noinspection PyTypeChecker
        ctrl: Optional[wx.Control] = None
        if prop_type is None:
            ctrl = None
        elif prop_type is wx.StaticLine:
            ctrl: wx.StaticLine = wx.StaticLine(self, wx.LI_HORIZONTAL)
        elif prop_type is wx.StaticText:
            ctrl: wx.StaticLine = wx.StaticText(self)
        elif prop_type == BasicDateText:
            if not third_state:
                ctrl: BasicDateText = BasicDateText(self, **kwargs)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self,BasicDateText, True, **kwargs)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicDatePicker:
            if not third_state:
                ctrl: BasicDatePicker = BasicDatePicker(self, **kwargs)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self, BasicDatePicker, True, **kwargs)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicCombobox:
            if 'style' in kwargs.keys():
                kwargs['style'] = kwargs['style'] | wx.CB_READONLY | wx.CB_SORT
            else:
                kwargs['style'] = wx.CB_READONLY | wx.CB_SORT
            if not third_state:
                ctrl: BasicCombobox = BasicCombobox(self, **kwargs)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self, BasicCombobox, True, **kwargs)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicCheckList:
            if not third_state:
                ctrl: BasicCheckList = BasicCheckList(self, **kwargs)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self, BasicCheckList, True,  **kwargs)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicList:
            if not third_state:
                ctrl: BasicList = BasicList(self, **kwargs)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self, BasicList, True,  **kwargs)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicCheckListWithFilter:
            if not third_state:
                ctrl: BasicCheckListWithFilter = BasicCheckListWithFilter(self, **kwargs)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self, BasicCheckListWithFilter, True, **kwargs)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicCheckBox:
            if not third_state:
                ctrl: BasicCheckBox = BasicCheckBox(self, False, False, **kwargs)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self, BasicCheckBox, True,  **kwargs)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicTextCtrl:
            if not third_state:
                ctrl: BasicTextCtrl = BasicTextCtrl(self,**kwargs)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self, BasicTextCtrl, True, **kwargs)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicFileSelect:
            if not third_state:
                ctrl: BasicFileSelect = BasicFileSelect(self, False, False, False)
            else:
                ctrl: BasicThirdStateControl = BasicThirdStateControl(self, BasicFileSelect, True,  show_relative_path=False,folder_select=False, can_drag_and_drop=False)
            ctrl.register_listener(self._event_listener)
        elif prop_type == BasicButton:
            ctrl:BasicButton  = BasicButton(self, label='')
            ctrl.register_listener(self._event_listener)
            #ctrl.Bind(wx.EVT_BUTTON, self._on_button_pressed)
        elif prop_type == BasicTwinTextCtrl:
            ctrl: BasicTwinTextCtrl = BasicTwinTextCtrl(self)
            ctrl.register_listener(self._event_listener)
            # ctrl.Bind(wx.EVT_BUTTON, self._on_button_pressed)
        else:
            mlogger.error(f'{self} При создании значения свойство типа {prop_type} не имеет соответствия с графическим компонентом')
        return ctrl


    def _property_set(self, prop_name: str, value: Any, available_values: Union[List[Tuple[str, Any]], str, Callable[[Any], List[Tuple[str, Any]]]]):
        if prop_name in self._control_types.keys():
            prop_type = type(self._controls[prop_name])
            if prop_type == BasicThirdStateControl:
                # noinspection PyTypeChecker
                ctrl: BasicThirdStateControl = self._controls[prop_name]
                prop_type = type(ctrl.get_control())
                if value == self.third_state_val(prop_type):
                    ctrl.is_third_state = True
                    return True
            else:
                if value == self.third_state_val(prop_type):
                    value = None



            if prop_type is wx.StaticText:
                # noinspection PyTypeChecker
                ctrl: wx.StaticText = self._controls[prop_name]
                try:
                    if value is None:
                        value = ''
                    ctrl_str = str(value)
                    ctrl.SetLabelText(ctrl_str)

                except Exception as ex:
                    mlogger.error(f'{self} Ошибка преобразования {value} {ex}')
                    return False
            elif prop_type is None:
                pass
            elif prop_type is wx.StaticLine:
                pass
            elif issubclass(prop_type, BasicControlWithList):
                # noinspection PyTypeChecker
                ctrl: BasicControlWithList = self._controls[prop_name]
                if available_values is not None:
                    if type(available_values) == list:
                        ctrl.set_available_values(available_values)
                    elif type(available_values) == callable:
                        ctrl.set_available_values(available_values())
                    else:
                        mlogger.error(f'{self} свойство {prop_name} перечень доступных элементов {type(available_values)} неизвестного типа')
                        return False
                if not ctrl.set_value(value):
                    mlogger.error(f'{self} ошибка установки значения {value} для элемента {prop_name} {prop_type}')
                    return False
            elif prop_type == BasicButton:
                pass
            elif prop_type in [BasicDateText, BasicDatePicker, BasicTextCtrl, BasicCheckBox, BasicFileSelect, BasicTwinTextCtrl]:
                # noinspection PyTypeChecker
                ctrl: Union[BasicDateText, BasicDatePicker, BasicTextCtrl, BasicCheckBox, BasicFileSelect, BasicTwinTextCtrl] = self._controls[prop_name]
                if not ctrl.set_value(value):
                    mlogger.error(f'{self} ошибка установки значения для элемента {prop_name} {prop_type}')
                    return False
            else:
                mlogger.error(f'{self} При установки значения {prop_name} свойство типа {prop_type} не имеет соответствия с графическим компонентом')
                return False
        else:
            mlogger.error(f'{self} Попытка присвоения свойству {prop_name} которое отсутствует среди доступных свойств')
            return False

        return True

    def _property_get(self, prop_name, avail_values: bool)->Any:
        t: wx.StaticText

        if prop_name in self._control_types.keys():
            prop_type = type(self._controls[prop_name])
            if prop_type == BasicThirdStateControl:
                # noinspection PyTypeChecker
                ctrl: BasicThirdStateControl = self._controls[prop_name]
                prop_type = type(ctrl.get_control())
                if ctrl.is_third_state:
                    return ctrl.get_value()

            if prop_type is wx.StaticText:
                pass
            elif prop_type is None:
                pass
            elif prop_type is wx.StaticLine:
                pass
            elif issubclass(prop_type, BasicControlWithList):
                # noinspection PyTypeChecker
                ctrl: BasicControlWithList = self._controls[prop_name]
                if not avail_values:
                    return ctrl.get_value()
                else:
                    return ctrl.get_available_values()
            elif prop_type == BasicButton:
                pass
            elif prop_type in [BasicDateText, BasicDatePicker, BasicTextCtrl, BasicCheckBox, BasicFileSelect, BasicTwinTextCtrl]:
                # noinspection PyTypeChecker
                ctrl: Union[BasicDateText, BasicDatePicker, BasicTextCtrl, BasicCheckBox, BasicFileSelect] = self._controls[prop_name]
                return ctrl.get_value()
            else:
                mlogger.error(f'{self} При чтении значения {prop_name} свойство типа {prop_type} не имеет соответствия с графическим компонентом')
        else:
            mlogger.error(f'{self} Попытка чтения свойства {prop_name} которое отсутствует среди доступных свойств')


    def _set_property_sizer_row(self, prop_name: str, row:int):
        if prop_name in self._controls.keys():
            st_text_ctrl = self._control_labels[prop_name]
            ctrl = self._controls[prop_name]
            if st_text_ctrl and ctrl:
                self._control_sizer.SetItemPosition(st_text_ctrl,(row,0))
                self._control_sizer.SetItemPosition(ctrl, (row, 1))
            elif ctrl:
                self._control_sizer.SetItemPosition(ctrl, (row, 0))

    def _get_property_sizer_row(self, prop_name: str):
        if prop_name in self._controls.keys():
            pos: wx.GBPosition = self._control_sizer.GetItemPosition(self._controls[prop_name])
            return pos.GetRow()
        return None

    def set_property_order(self, prop_name: str, new_row_index: int):
        if prop_name not in self._control_types.keys():
            mlogger.error(f'{self} set_property_order не найден параметр {prop_name} ')
            return

        # сохраним изменяемые размеры строк во временнюу перменную
        old_growable_rows = []

        for name in self._controls.keys():
            row_number = self._get_property_sizer_row(name)
            if self._control_sizer.IsRowGrowable(row_number):
                old_growable_rows.append(name)

        # приступим к изменению порядка строк
        row_count = len(self._controls.keys())
        if new_row_index<0:
            new_row_index = 0
        if new_row_index>=row_count:
            new_row_index = row_count - 1

        old_row_index = self._get_property_sizer_row(prop_name)
        if new_row_index == old_row_index:
            return

        names_order: List[Tuple[int, str]] = []
        for name in self._controls.keys():
            cur_index = self._get_property_sizer_row(name)
            names_order.append((cur_index, name))

        self._set_property_sizer_row(prop_name, row_count+2)


        names_order.sort(key=lambda x:x[0])
        for index, name in reversed(names_order):
            if index>=new_row_index and name != prop_name:
                self._set_property_sizer_row(name, index+1)

        for index, name in names_order:
            if index>old_row_index and name != prop_name:
                if new_row_index>old_row_index:
                    self._set_property_sizer_row(name, index-1)
                else:
                    self._set_property_sizer_row(name, index)
        self._set_property_sizer_row(prop_name, new_row_index)


        # установим значение изменяемых строк в таблицу
        for name in self._controls.keys():
            row_number = self._get_property_sizer_row(name)
            if name in old_growable_rows:
                if not self._control_sizer.IsRowGrowable(row_number):
                    self._control_sizer.AddGrowableRow(row_number, 0)
            else:
                if self._control_sizer.IsRowGrowable(row_number):
                    self._control_sizer.RemoveGrowableRow(row_number)
        #
        #
        #if static_text_ctrl and ctrl: # если есть наименование параметра, то добавим его
        #    self._control_sizer.SetItemPosition(static_text_ctrl, (pos_row,0))
        #    self._control_sizer.SetItemPosition(ctrl, (pos_row, 1))
        #    self._control_sizer.Layout()
        #else: # если нет параметра
        #    if ctrl: #и если есть контрол
        #        self._control_sizer.SetItemPosition(ctrl, (pos_row, 0))
        #        self._control_sizer.Layout()
        #    else:
        #        mlogger.error(f'{self} ошибка создания длинного компонента')


    def _property_add(self, prop_name: str, prop_title: Optional[str], prop_type: Union[Type, None], third_state: bool, **kwargs):
        if prop_name not in self._controls.keys() and prop_name not in self._control_labels.keys():
            ctrl = self._property_builder(prop_type, third_state,  **kwargs)
            if third_state:
                self._control_with_third_state.append(prop_name)
            static_text_ctrl = None
            if ctrl is None and prop_type is not None:
                mlogger.error(f'{self} для свойства {prop_name} объект не создан, ctrl не создан')
                return
            elif prop_title is not None and type(prop_title) == str and prop_type is None:
                ctrl = wx.StaticText(self)
                ctrl.SetLabel(prop_title)
            elif prop_title is None and prop_type == wx.StaticLine:
                pass
            elif ctrl is not None and prop_type is not None:
                if prop_title:
                    static_text_ctrl = wx.StaticText(self)
                    static_text_ctrl.SetLabel(prop_title)
            else:
                mlogger.error(f'{self} для свойства {prop_name} объект не создан, неверное сочетание:{prop_title} и {prop_type}')
                return

            pos_row = len(self._controls)

            self._controls[prop_name] = ctrl
            self._control_labels[prop_name] = static_text_ctrl


            # добавим наименование параметра в строку

            control_flags = wx.ALIGN_LEFT  | wx.ALL | wx.EXPAND
            #if self.sizeable:
            #    control_flags = control_flags | wx.EXPAND

            if static_text_ctrl: # если есть наименование параметра, то добавим его
                label_flags = wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL | wx.ALL # сориентируем наименование параметра вправо
                self._control_sizer.Add(self._control_labels[prop_name], pos=(pos_row, 0), flag=label_flags, border=self._border)
                self._control_sizer.Add(self._controls[prop_name], pos=(pos_row, 1), flag=control_flags, border=self._border)
                if issubclass(type(self._controls[prop_name]), BasicControlWithList) and not issubclass(type(self._controls[prop_name]), BasicCombobox):
                    if not self._control_sizer.IsRowGrowable(pos_row):
                        self._control_sizer.AddGrowableRow(pos_row, 0)


            else: # если нет параметра
                if self._controls[prop_name]: #и если есть контрол
                    static_flags = wx.ALIGN_LEFT  | wx.ALL | wx.EXPAND
                    self._control_sizer.Add(self._controls[prop_name], pos=(pos_row, 0), span=(1, 2), flag=static_flags, border=self._border)
                    if issubclass(type(self._controls[prop_name]), BasicControlWithList) and not issubclass(type(self._controls[prop_name]), BasicCombobox):
                        if not self._control_sizer.IsRowGrowable(pos_row):
                            self._control_sizer.AddGrowableRow(pos_row, 0)
                else:
                    mlogger.error(f'{self} ошибка создания длинного компонента')

            #if not self._control_sizer.IsColGrowable(0):
            #    self._control_sizer.AddGrowableCol(0)

            if not self._control_sizer.IsColGrowable(1):
                self._control_sizer.AddGrowableCol(1)
        else:
            mlogger.error(f'{self} повреждение структуры объекта, {prop_name} уже добавлен')

    # region Основная работа со свойствами


    def have_property(self, prop_name: str):
        return prop_name in self._controls.keys()



    def add_property(self, prop_name: str, prop_title: Optional[str], prop_type: Union[Type, None], third_state: bool, **kwargs):
        new_prop_type = prop_type
        if prop_type in [int, float, str]:
            new_prop_type = BasicTextCtrl
        elif prop_type == datetime.date:
            new_prop_type = BasicDatePicker
        elif prop_type == bool:
            new_prop_type = BasicCheckBox
        elif prop_type == Tuple[float, float]:
            new_prop_type = BasicTwinTextCtrl
        elif prop_type == List[str]:
            new_prop_type = BasicTextCtrl
            style = 0
            if 'style' in kwargs.keys():
                style = kwargs['style']
            style |= wx.TE_MULTILINE
            kwargs['style'] = style
        self._property_add(prop_name, prop_title, new_prop_type, third_state, **kwargs)
        self._control_types[prop_name] = prop_type


    def third_state_val(self, prop_type: Type):
        if prop_type in [int, float, str]:
            return BasicTextCtrl
        elif prop_type == datetime.date:
            return BasicDatePicker
        elif prop_type == bool:
            return BasicCheckBox
        elif prop_type == List[str]:
            return BasicTextCtrl
        elif prop_type in BasicThirdStateControl.available_types:
            return prop_type
        else:
            mlogger.debug(f'{self} get_third_state_value неизвестный тип для типа свойства {prop_type} ')
            return None


    def get_property(self, prop_name: str, avail_values: bool)->Any:
        if prop_name not in self._control_types.keys():
            mlogger.error(f'{self} get_property не найден параметр {prop_name} ')
            return None
        prop_type = self._control_types[prop_name]
        return_val = self._property_get(prop_name, avail_values)
        if return_val is None:
            return return_val
        if prop_type in [int, float, str]:
            if prop_type == int:
                try:
                    return_val = locale.atoi(return_val)
                except Exception as ex:
                    mlogger.error(f'{self} get_property {return_val} ошибка преобразования {ex}')
                    return None
            elif prop_type == float:
                try:
                    return_val = locale.atof(return_val)
                except Exception as ex:
                    mlogger.error(f'{self} get_property {return_val} ошибка преобразования {ex}')
                    return None
        elif prop_type == datetime.date:
            pass
        elif prop_type == bool:
            pass
        elif prop_type == Tuple[float, float]:
            v1, v2 = return_val
            try:
                v1 = locale.atof(v1)
                v2 = locale.atof(v2)
                return_val = v1, v2
            except Exception as ex:
                mlogger.error(f'{self} get_property {return_val} ошибка преобразования {v1} {v2} {ex}')
                return None

        elif prop_type == List[str]:
            try:
                return_val = return_val.split('\n')
            except Exception as ex:
                mlogger.error(f'{self} get_property {return_val} ошибка преобразования {ex}')
                return None
        return return_val



    def set_property(self, prop_name: str, value: Any, avail_values: Optional[List[Tuple[str, Any]]]):
        #print(f'Установка значения {prop_name} {value} {avail_values}')
        if prop_name not in self._control_types.keys():
            mlogger.error(f'{self} set_property не найден параметр {prop_name} ')
            return False
        prop_type = self._control_types[prop_name]
        if value is not None:
            if prop_type in [int, float, str]:
                if prop_type in [int, float]:
                    try:
                        value = locale.str(value)
                    except Exception as ex:
                        mlogger.error(f'{self} set_property {value} ошибка преобразования {ex}')
                        return False
            elif prop_type == datetime.date:
                pass
            elif prop_type == bool:
                pass
            elif prop_type == Tuple[float, float]:
                if type(value) in [tuple, list]:
                    try:
                        if len(value)>=0:
                            value = locale.str(value[0]), locale.str(value[1])
                        else:
                            mlogger.error(f'{self} set_property {value} не является tuple')
                            return False
                    except Exception as ex:
                        value = None, None
                        mlogger.error(f'{self} set_property {value} ошибка преобразования {ex}')
                        return False
                else:
                    mlogger.error(f'{self} set_property {value} не является tuple')
                    return False
            elif prop_type == List[str]:
                if type(value) == list:
                    value = '\n'.join([v_str for v_str in list(value)])
                else:
                    mlogger.error(f'{self} set_property {value} не является списком')
                    return False
        return self._property_set(prop_name, value, avail_values)

    def set_property_param(self, prop_name: str, param_name: str, value: Any):
        if prop_name in self._controls.keys():
            # noinspection PyTypeChecker
            ctrl = self._controls[prop_name]
            if not hasattr(ctrl, param_name):
                if issubclass(type(ctrl), BasicThirdStateControl):
                    ctrl: BasicThirdStateControl
                    # noinspection PyTypeChecker
                    ctrl = ctrl.get_control()
            if hasattr(ctrl, param_name):
                try:
                    setattr(ctrl, param_name, value)
                except Exception as ex:
                    mlogger.error(f'{self} set_property_param {prop_name} для парамтера {param_name} невозможно установить значение {value} по причине {ex}')
            else:
                mlogger.error(f'{self} set_property_param {prop_name} не найден параметр {param_name}')
        else:
            mlogger.error(f'{self} set_property_param не найден контрол для {prop_name}')

    #endregion

    @property
    def notify(self):
        return self._notify_changes

    @notify.setter
    def notify(self, val: bool):
        if type(val) == bool:
            self._notify_changes = val

    def set_property_size(self, prop_name: str, width: int, height:int):
        self._set_control_size(prop_name, width, height)
        #if prop_name in self._controls.keys() and prop_name in self._control_labels.keys():
        #    flags = self._sizer_items[prop_name][prop_index].GetFlag()
        #    if self.sizeable and width<0:
        #        flags = flags | wx.EXPAND
        #    else:
        #        flags = flags & ~wx.EXPAND
        #    self._sizer_items[prop_name][prop_index].SetFlag(flags)
        #    ctrl = self._controls[prop_name]
        #    ctrl_size = wx.Size(width, height)
        #    # внимание! просто установка размеров не приведет к корректному расположению элементов
        #    ctrl.SetMinSize(ctrl_size)
        #    ctrl.SetMaxSize(ctrl_size)
        #    ctrl.SetSize(ctrl_size)
        #    self.Layout()
        #    self.Update()
        #else:
        #    mlogger.error(f'{self} set_property_size повреждение структуры объекта, {prop_name} не найдено в self._controls, self._control_labels')

    #def set_property_best_size(self, prop_name: str):
    #    print(f'{self} Раньше здесь было set_property_best_size')

    def _get_control_min_size(self, prop_name: str)->Optional[wx.Size]:
        if prop_name in self._controls.keys() and prop_name in self._control_labels.keys():
            # noinspection PyTypeChecker
            ctrl = self.get_control(prop_name)
            if ctrl is None:
                mlogger.error(f'{self} _set_control_size повреждение структуры объекта, не найден gui элемент')
                return None
            if issubclass(type(ctrl), BasicTextCtrl):
                ctrl: BasicThirdStateControl = ctrl
                return ctrl.get_min_size()
            else:
                return ctrl.GetMinSize()
        else:
            mlogger.error(f'{self} _set_control_size повреждение структуры объекта, {prop_name} не найдено в self._controls, self._control_labels')
        return None

    def _set_control_size(self,prop_name: str, width: int, height: int):
        if prop_name in self._controls.keys() and prop_name in self._control_labels.keys():
            ctrl = self.get_control(prop_name)
            if ctrl is None:
                mlogger.error(f'{self} _set_control_size повреждение структуры объекта, не найден gui элемент')
                return
            #min_size = self._get_control_min_size(prop_name)
            ctrl_width = width
            ctrl_height = height

            if ctrl_width<=0:
                ctrl_width = 10
            #if ctrl_height<=0:
            #    ctrl_height = 10
            ctrl.SetMinSize(wx.Size(ctrl_width, ctrl_height))
            #item_row = list(self._controls.keys()).index(prop_name)
            sizer_item: wx.GBSizerItem = self._control_sizer.FindItem(ctrl)
            if sizer_item:
                if width == -1:
                    flags = sizer_item.GetFlag()
                    flags |= wx.EXPAND
                    sizer_item.SetFlag(flags)
                else:
                    flags = sizer_item.GetFlag()
                    flags &= ~wx.EXPAND
                    sizer_item.SetFlag(flags)
            else:
                mlogger.error(f'{self} не найден сайзер для {prop_name}')
            self.update_view()

        else:
            mlogger.error(f'{self} _set_control_size повреждение структуры объекта, {prop_name} не найдено в self._controls, self._control_labels')
        self.Layout()
        self.Update()

    def set_property_label_name(self, prop_name: str, prop_label_name: str):
        if prop_name in self._control_types.keys():
            # noinspection PyTypeChecker
            ctrl: wx.CheckBox = self._controls[prop_name]
            if issubclass(type(ctrl), wx.CheckBox):
                ctrl.SetLabel(prop_label_name)


    def is_property_enabled(self, prop_name: str):
        if prop_name in self._controls.keys():
            if type(self._controls[prop_name]) == BasicCheckListWithFilter:
                # noinspection PyTypeChecker
                ctrl: BasicCheckListWithFilter = self._controls[prop_name]
                return ctrl.is_control_enabled()
            else:
                return self._controls[prop_name].IsEnabled()
        mlogger.error(f'{self} is_property_enabled не найден элемент для {prop_name}')
        return False

    def enable_property(self, prop_name: str, enable: bool):
        if prop_name in self._controls.keys():
            if type(self._controls[prop_name]) == BasicCheckListWithFilter:
                # noinspection PyTypeChecker
                ctrl: BasicCheckListWithFilter = self._controls[prop_name]
                ctrl.enable_control(enable)
            else:
                self._controls[prop_name].Enable(enable)
        else:
            mlogger.error(f'{self} enable_property не найден элемент для {prop_name}')

    def show_property(self, prop_name: str, show: bool, update_now: bool=True):
        if prop_name in self._controls.keys():
            if self._controls[prop_name]:
                self._controls[prop_name].Show(show)
        if prop_name in self._control_labels.keys():
            if self._control_labels[prop_name]:
                self._control_labels[prop_name].Show(show)
        if update_now:
            self._control_sizer.Layout()
            #self.main_sizer.Layout()
            self.Fit()
            self.update_view()
            self.Update()

    def is_proprty_visible(self, prop_name: str):
        if prop_name in self._controls.keys():
            return self._controls[prop_name].IsShown()
        return False

    def get_property_type(self, prop_name: str):
        if prop_name in self._control_types.keys():
            return self._control_types[prop_name]

    def get_control(self, prop_name: str)->Optional[wx.Control]:
        if prop_name in self._controls.keys():
            return self._controls[prop_name]
        return None

    #def get_property_avail_values(self, prop_name: str)->Optional[List[Any]]:
    #    if prop_name in self._controls.keys():
    #        # prop_type = self.control_types[prop_name]
    #        return self._property_get(prop_name, True)
    #    return None

    def get_param_names(self):
        return list(self._controls.keys())

    def set_focus(self):
        if len(self._controls) > 0:
            ctrl_names = list(self._controls.keys())
            for i in range(len(self._controls)):
                if ctrl_names[i] in self._controls.keys():
                    if self._controls[ctrl_names[i]]:
                        # noinspection PyTypeChecker
                        ctrl = self._controls[ctrl_names[i]]
                        if ctrl:
                            ctrl.NavigateIn()
                            ctrl.SetFocus()
                            ctrl.SetFocusFromKbd()
                            ctrl: BasicTextCtrl
                            if type(ctrl) == wx.TextCtrl:
                                ctrl.SetInsertionPoint(0)
                                ctrl.SetSelection(0, len(ctrl.GetValue()))
                            #elif issubclass(type(ctrl), wx.ComboBox):
                            #    ctrl: wx.ComboBox
                            #    ctrl.Popup()
                            #    ctrl.Dismiss()
                            break
                        else:
                            mlogger.error(f'{self} не найден control для {ctrl_names[i]}')

    def clear(self):
        self._controls.clear()
        self._control_labels.clear()
        self._control_sizer.Clear(True)
        self._control_types.clear()

    def update_view(self):
        """ Функция для обновления скроллинга, после добавления удаления элементов"""
        #if self.scrollable:
        #    self.SetVirtualSize(self.GetMinSize())
        #    self.SendSizeEvent()

        self._control_sizer.Fit(self)
        self._control_sizer.Layout()
        #self.main_sizer.Layout()
        #if not self.sizeable:
        #    self.Fit()
        #self.Refresh()
        #self.Layout()





class InputBox(BasicDialog):
    scrollable: bool = False
    sizeable: bool = False

    _main_sizer: wx.BoxSizer
    _info_ctrl: BasicInfoBar
    input_panel: InputOutputPanel

    _btn_ok: wx.Button
    _btn_cancel: wx.Button

    on_ok_button: Optional[Callable[[None], None]]
    on_cancel_button: Optional[Callable[[None], None]]

    _parent: Any
    def __init__(self, parent:Union[wx.Frame, wx.Panel, wx.ScrolledCanvas, wx.Dialog, wx.PopupTransientWindow, 'InputBox', 'DBInputDialog'], title: str, image_path: str = None, ini_file: configparser.ConfigParser=None, pos: wx.Position = wx.DefaultPosition, size: wx.Size = wx.DefaultSize, scrollable: bool = False, sizeable: bool = False, ignore_enter_key: bool = True, style=wx.DEFAULT_DIALOG_STYLE, show_buttons: bool = True):
        self._parent = parent
        BasicDialog.__init__(self, parent, title, image_path, wx.Point(pos.Get()[0], pos.Get()[1]), size, ini_file, sizeable, style | wx.PD_APP_MODAL)
        self.scrollable = scrollable
        self.sizeable = sizeable
        self._main_sizer = wx.BoxSizer(wx.VERTICAL)
        self._info_ctrl = BasicInfoBar(self)
        self.on_ok_button = None
        self.on_cancel_button = None
        if show_buttons:
            self.btnsizer = wx.StdDialogButtonSizer()
            self._btn_ok = wx.Button(self, wx.ID_OK)
            self._btn_ok.Bind(wx.EVT_BUTTON, self._ok_button_click)
            if not ignore_enter_key:
                self._btn_ok.SetDefault()
            self.btnsizer.AddButton(self._btn_ok)
            self._btn_cancel = wx.Button(self, wx.ID_CANCEL)
            self._btn_cancel.Bind(wx.EVT_BUTTON, self._cancel_button_click)
            #self.btn_cancel.SetDefault()
            self.btnsizer.AddButton(self._btn_cancel)
            self.btnsizer.Realize()

        self.input_panel = InputOutputPanel(self, False, scrollable, border=3)

        self._main_sizer.Add(self._info_ctrl, 0, wx.ALL | wx.EXPAND, 0)
        self._main_sizer.Add(self.input_panel, 1, wx.ALL | wx.EXPAND, 2)


        if show_buttons:
            self._main_sizer.Add(self.btnsizer, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 10)
        self.SetSizer(self._main_sizer)
        if not self.scrollable:
            self.SetMinSize(size)
            self.Layout()
            self.Fit()
        else:
            # Внимание! если не вызвать установку размеров после отработки __init__ размеры почему-то не устанавливаются ! глюк wxWidgets
            #wx.CallAfter(self.SetSize, size)
            self.SetMinSize(size)
            self.SetSize(size)
            self.SendSizeEvent()
            #self.SetSize(size)
            #self.Layout()
        if not ini_file:
            self.CenterOnParent()
        self.load_state()

    @property
    def parent(self):
        return self._parent

    def _ok_button_click(self, evt: wx.CommandEvent):
        if self.on_ok_button:
            self.on_ok_button()
        evt.Skip()
    def _cancel_button_click(self, evt: wx.CommandEvent):
        if self.on_cancel_button:
            self.on_cancel_button()
        evt.Skip()


    def _on_close(self, evt: wx.CloseEvent):
        BasicDialog._on_close(self, evt)

    def enable_ok_button(self, enable: bool):
        self._btn_ok.Enable(enable)

    def get_min_height(self):
        # noinspection PyProtectedMember
        return self._main_sizer.GetMinSize().GetHeight()+self.input_panel._control_sizer.GetMinSize().GetHeight()+self.btnsizer.GetMinSize().GetHeight()+15


    def show_info_message(self, msg: str, icon: int, can_close: bool = False):
        self._info_ctrl.show_message(msg, icon, can_close)

    def hide_info_message(self):
        self._info_ctrl.hide()

    def add_button_info_message(self, label: str, callback: Callable):
        self._info_ctrl.add_button(label, callback)

    def clear_buttons_info_message(self):
        self._info_ctrl.clear_buttons()

    def have_button(self, label: str):
        return self._info_ctrl.have_button(label)

class DBInputDialogConfig:
    field_name: str
    field_type: Type
    description: str
    width: int
    height: int
    formatter_func: Optional[Callable]
    list_values: Optional[Union[List[Tuple[str, Any]], Callable[[Any], List[Tuple[str, Any]]]]]
    third_state: bool

    def __init__(self, field_name: str, field_type: Optional[Type], description: str, third_state: bool, width: int=-1, height: int=-1, formatter_func: Callable = None, list_values: Optional[Union[List[Any], str]] = None):
        self.field_type = field_type
        self.field_name = field_name
        self.description = description
        self.width = width
        self.height = height
        self.formatter_func = formatter_func
        self.list_values = list_values
        self.third_state = third_state

class DBInputDialog(InputBox):

    dialog_config: List[DBInputDialogConfig]
    input_panel: InputOutputPanel
    logger: Logger
    _parent: Any
    def __init__(self, parent: Union[wx.Frame, wx.Panel, wx.ScrolledCanvas, wx.Dialog], title: str,  ini_file: configparser.ConfigParser = None, dialog_config: List[DBInputDialogConfig]=None,size: wx.Size = wx.DefaultSize, sizeable: bool = False, scrollable:bool=False, logger: Logger = Logger()):
        self._parent = parent
        InputBox.__init__(self,parent, title, None, ini_file, size=size, sizeable=sizeable, scrollable=scrollable, ignore_enter_key=False)
        self.dialog_config = dialog_config
        self.logger = logger


    def create_items(self):
        cfg: DBInputDialogConfig
        for cfg in self.dialog_config:
            self.input_panel.add_property(cfg.field_name, cfg.description, cfg.field_type, cfg.third_state)
            self.input_panel.set_property_size(cfg.field_name, cfg.width, cfg.height)
            if cfg.list_values:
                if not cfg.formatter_func:
                    self.input_panel.set_property(cfg.field_name,None, cfg.list_values)
                else:
                    self.input_panel.set_property(cfg.field_name, None, None)
        if self.dialog_config:
            self.input_panel.set_focus()
        self.input_panel.update_view()
        if not self.sizeable and not self.scrollable:
            self.Fit()


    def save_to_item(self, item: DBStorableRow):
        cfg: DBInputDialogConfig
        props = item.get_properties()

        for cfg in self.dialog_config:
            if cfg.field_name in props.keys():
                if not self.input_panel.is_proprty_visible(cfg.field_name):
                    continue
                #third_state = self.input_panel.third_state_val(cfg.field_type)
                if cfg.field_type in [str, int, float, bool, datetime.date, datetime.datetime, BasicFileSelect, BasicCheckBox, List[str]]:
                    save_value = self.input_panel.get_property(cfg.field_name, False)
                    setattr(item, cfg.field_name, save_value)
                #elif cfg.field_type == List[str]:
                #    save_value = self.input_panel.get_property(cfg.field_name, False)
                #    if props[cfg.field_name][0] == PropertyType.LIST_SPLITTED and props[cfg.field_name][1] == str:
                #        if save_value:
                #            setattr(item, cfg.field_name, save_value.split('\n'))
                #        else:
                #            setattr(item, cfg.field_name, [])
                #    elif props[cfg.field_name][0] == PropertyType.GENERIC and props[cfg.field_name][1] == str:
                #        setattr(item, cfg.field_name, save_value)
                elif cfg.field_type is None:
                    save_value = self.input_panel.get_property(cfg.field_name, False)
                    setattr(item, cfg.field_name, save_value)
                #elif cfg.field_type == BasicDatePickerThirdState:
                #    setattr(item, cfg.field_name, self.input_panel.get_property(cfg.field_name))
                elif cfg.field_type in [BasicCombobox, BasicCheckList, BasicCheckListWithFilter]:
                    save_value = self.input_panel.get_property(cfg.field_name, False)
                    if issubclass(item.__class__, DBStorableRow):
                        if props[cfg.field_name][0] in [PropertyType.CLASS_INSTANCE, PropertyType.ENUM]:
                            setattr(item, cfg.field_name, save_value)
                        #elif props[cfg.field_name][0] == PropertyType.LIST_CLASS_INSTANCE:
                        #    list_items:DBStorableList = getattr(item, cfg.field_name)
                        #    save_value: List[DBStorableRow]
                        #    cur_items = list(list_items.get_items())
                        #    for val in cur_items:
                        #        if val not in save_value:
                        #            list_items.remove(val)
                        #    for val in list(save_value):
                        #        if val not in cur_items:
                        #            list_items.append(val)
                        elif props[cfg.field_name][0] == PropertyType.LIST_SPLITTED:
                            setattr(item, cfg.field_name, save_value)
                        else:
                            self.logger.error(f'{self} При сохранении объект {type(item)} свойство {cfg.field_name} типа {cfg.field_type} не имеет функции сохранения значений')
                    else:
                        self.logger.error(f'{self} При сохранении объект {type(item)} свойство {cfg.field_name} типа {cfg.field_type} имеет неверный тип BasicCombobox')
                else:
                    self.logger.error(f'{self} При сохранении объекта {type(item)} не имеет свойства {cfg.field_name} {item}')
            else:
                self.logger.error(f'{self} При сохранении объекта {type(item)} не имеет свойства {cfg.field_name} {item} в классе')



    def load_from_item(self, item: DBStorableRow):
        cfg: DBInputDialogConfig
        props = item.get_properties()
        for cfg in self.dialog_config:
            if cfg.field_name in props.keys():
                if not self.input_panel.is_proprty_visible(cfg.field_name):
                    continue
                # noinspection PyTypeChecker
                third_state = self.input_panel.third_state_val(cfg.field_type)
                if cfg.field_type in [str, int, float, bool, datetime.date, datetime.datetime, BasicFileSelect, BasicCheckBox, List[str]]:
                    if not hasattr(item, cfg.field_name):
                        self.input_panel.set_property(cfg.field_name, third_state, None)
                    else:
                        self.input_panel.set_property(cfg.field_name, getattr(item, cfg.field_name), None)
                #elif cfg.field_type == List[str]:
                #    val = getattr(item, cfg.field_name)
                #    if val:
                #        val = '\n'.join([str(item) for item in val])
                #    self.input_panel.set_property(cfg.field_name, val, None)
                elif cfg.field_type is None:
                    if cfg.formatter_func is not None:
                        prop_value = cfg.formatter_func(getattr(item, cfg.field_name))
                    else:
                        prop_value = getattr(item, cfg.field_name)
                    if not hasattr(item, cfg.field_name):
                        self.input_panel.set_property(cfg.field_name, third_state, None)
                    else:
                        self.input_panel.set_property(cfg.field_name, prop_value, None)
                #elif cfg.field_type == BasicDatePickerThirdState:
                #    self.input_panel.set_property(cfg.field_name, getattr(item, cfg.field_name), cfg.list_values)
                elif cfg.field_type in [BasicCombobox, BasicCheckList, BasicCheckListWithFilter]:
                    if issubclass(item.__class__, DBStorableRow) or issubclass(item.__class__, Enum):
                        avail_values = None
                        if cfg.list_values:
                            if cfg.formatter_func:
                                avail_values = [(cfg.formatter_func(value), value) for value in cfg.list_values]
                        else:
                            ref_table_type = props[cfg.field_name][1]
                            if ref_table_type is not None:
                                ref_table = item.table.dataset.get_table(ref_table_type)
                                if ref_table is not None and cfg.formatter_func is not None:
                                    avail_values = [(cfg.formatter_func(value), value) for value in ref_table.get_items()]
                        if props[cfg.field_name][0] in [PropertyType.CLASS_INSTANCE, PropertyType.ENUM]:
                            if hasattr(item, cfg.field_name):
                                cur_value = getattr(item, cfg.field_name)
                            else:
                                cur_value = None
                        elif props[cfg.field_name][0] == PropertyType.LIST_SPLITTED:
                            if hasattr(item, cfg.field_name):
                                cur_value = getattr(item, cfg.field_name)
                            else:
                                cur_value = None
                        else:
                            cur_value = None
                            self.logger.error(f'{self} При загрузке объект {type(item)} свойство {cfg.field_name} типа {cfg.field_type} не имеет функции загрузки значений')
                        if not hasattr(item, cfg.field_name):
                            self.input_panel.set_property(cfg.field_name, third_state, avail_values)
                        else:
                            self.input_panel.set_property(cfg.field_name, cur_value, avail_values)
                    else:
                        self.logger.error(f'{self} При загрузке объект {type(item)} свойство {cfg.field_name} типа {cfg.field_type} имеет неверный тип BasicCombobox')
                else:
                    self.logger.error(f'{self} При загрузке объект {type(item)} свойство {cfg.field_name} типа {cfg.field_type} не имеет преобразования')

            else:
                self.logger.error(f'{self} При загрузке объект {type(item)} не имеет свойства {cfg.field_name} {item}')

import wx.lib.agw.pygauge as pygauge



class ProgressWnd(BasicDialog, EventSubscriber): #BasicWindow, EventSubscriber):
    """ВНИМАНИЕ: любые попытки использовать потоки ни к чему хорошему не привели. Обновление только по событию"""
    #modal = None
    main_panel: wx.Panel
    main_sizer: wx.BoxSizer
    _used_levels: List[int]
    _used_control: Dict[int, Tuple[wx.Panel, wx.BoxSizer, wx.StaticLine, wx.StaticText, Union[wx.Gauge, pygauge]]]
    use_pygauge  = True
    _notifier: EventPublisher
    _use_timer: bool
    _start_time: datetime.datetime
    def __init__(self, parent: Union[wx.Frame, wx.Panel, wx.Dialog, wx.Control, wx.grid.Grid], window_name: str, size: wx.Size = wx.Size(200, 10), show_timer: bool = False):
        self._parent = parent
        style = wx.CAPTION | wx.FRAME_NO_TASKBAR | wx.FRAME_FLOAT_ON_PARENT
        #BasicWindow.__init__(self, parent, window_name, None, None, None, size, False, True, False, style)
        #BasicDialog.__init__(self, parent, window_name, None, None, None, size, False, True, False, style)
        BasicDialog.__init__(self, parent, window_name, None, wx.DefaultPosition, size, None, False, style | wx.PD_APP_MODAL)

        EventSubscriber.__init__(self)
        wnd_sizer = wx.BoxSizer(wx.VERTICAL)
        self.main_panel = wx.Panel(self)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        wnd_sizer.Add(self.main_panel, 1, wx.EXPAND, 0)
        self.main_panel.SetSizer(self.main_sizer)
        self.SetSizer(wnd_sizer)

        self.SetMinSize(size)
        self.Layout()
        self.CenterOnParent()
        #self.modal = wx.WindowDisabler()
        self._used_levels = []
        self._used_controls = {}
        self._notifier = EventPublisher()
        self._notifier.register_listener(self)
        self._use_timer = show_timer
        if self._use_timer:
            self._timer_label = wx.StaticText(self.main_panel)
            self._used_levels.append(-1)
            self._used_controls[-1] = self._timer_label
            self.main_sizer.Add(self._timer_label, 0, wx.ALL, 0)
            self._start_time = datetime.datetime.now()

    def show_msg(self, msg: str):
        evt = EventProgressObject(msg, level=0)
        self.on_notify(EventType.OPERATION_BEGIN, evt)

    def get_notifier(self):
        return self._notifier



    #def on_close(self, event: wx.CloseEvent):
    #    BasicDialog.on_close(self, event)
    #    #del self.modal
    #    #wx.CallAfter(self.parent.SetFocus)

    @WxEvents.debounce(0.5,True)
    def update_state(self):
        #wx.Yield()
        ctrl_data: Tuple[wx.Panel, wx.BoxSizer, wx.StaticLine, wx.StaticText, Union[wx.Gauge, pygauge]]
        if self._use_timer:
            t_delta = (datetime.datetime.now() - self._start_time)
            self._timer_label.SetLabel(f'Прошло: {t_delta.seconds+1} сек.')
            self._timer_label.Update()
        for ctrl_data in self._used_controls.values():
            if type(ctrl_data) == tuple:
                if ctrl_data[3]:
                    ctrl_data[3].Refresh()
                    ctrl_data[3].Update()
                if ctrl_data[4]:
                    ctrl_data[4].Refresh()
                    #ctrl_data[4].Update()
        self.Refresh()
        self.Update()
        wx.SafeYield(self)

    def on_notify(self, event_type: EventType, event_object: Union[EventObject, EventProgressObject]):
        EventSubscriber.on_notify(self, event_type, event_object)
        #print(f'progresswnd on_nofity')
        if event_type in [EventType.OPERATION_BEGIN, EventType.OPERATION_STEP, EventType.OPERATION_END]:
            # noinspection PyTypeChecker
            p_event: EventProgressObject = event_object

            insert_pos = None
            if p_event.level not in self._used_levels:
                insert_pos = bisect.bisect_right(self._used_levels, p_event.level)
            msg_ctrl: wx.StaticText
            update_sizer = False
            if insert_pos is not None:
                panel, sizer, line, msg, gauge = ProgressWnd.create_items(self.main_panel)
                if len(self._used_levels)>0:
                    self.main_sizer.Insert(insert_pos, panel, 1, wx.EXPAND, 1)
                else:
                    self.main_sizer.Add(panel,1, wx.EXPAND, 1)
                update_sizer = True
                self._used_controls[p_event.level] = panel, sizer, line, msg, gauge
                self._used_levels.insert(insert_pos, p_event.level)

            else:
                panel, sizer, line, msg, gauge = self._used_controls[p_event.level]
            have_msg = False
            need_panel_layout = False
            if p_event.msg is None or len(p_event.msg)==0:
                if msg.IsShown():
                    msg.Hide()
                    need_panel_layout = True
            else:
                msg.SetLabelText(p_event.msg)
                if not msg.IsShown():
                    msg.Show()
                    need_panel_layout = True
                have_msg = True


            have_progress = False
            if p_event.max_val is not None:
                if p_event.max_val>0:
                    gauge.SetRange(p_event.max_val)
                else:
                    gauge.SetRange(1)
                if 0<=p_event.cur_val<=p_event.max_val:
                    gauge.SetValue(p_event.cur_val)
                else:
                    gauge.SetValue(1)
                have_progress = True
                if not gauge.IsShown():
                    gauge.Show()
                    need_panel_layout = True
            else:
                if gauge.IsShown():
                    gauge.Hide()
                    need_panel_layout = True

            if have_msg or have_progress:
                if have_progress:
                    gauge.Refresh()
                if not panel.IsShown():
                    panel.Show()
                    need_panel_layout = True
            else:
                if panel.IsShown():
                    panel.Hide()
                    need_panel_layout = True

            if need_panel_layout or update_sizer:
                #panel.Layout()
                sizer.Layout()
                panel.Fit()
                panel.Update()
                panel.Refresh()
                #sizer.Layout()
                self.main_sizer.Layout()
                self.main_panel.Update()
                self.main_panel.Refresh()
                self.Update()
                self.Fit()
                self.Refresh()
                #wx.Yield()
                #self.SendSizeEvent()
            # noinspection PyArgumentList
            self.update_state()

    @staticmethod
    def set_busy_cursor(busy: bool):
        if busy:
            if not wx.IsBusy():
                wx.BeginBusyCursor()
        else:
            if wx.IsBusy():
                wx.EndBusyCursor()



    @classmethod
    def create_items(cls, parent: Any):
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)
        static_line = wx.StaticLine(panel)
        msg_ctrl = wx.StaticText(panel)
        if not ProgressWnd.use_pygauge:
            gauge_ctrl = wx.Gauge(panel)
        else:
            gauge_ctrl = pygauge.PyGauge(panel)
            gauge_ctrl.SetMinSize(wx.Size(-1, 20))
            gauge_ctrl.SetMaxSize(wx.Size(-1, 20))
            gauge_ctrl.SetBarColor(wx.GREEN)
            gauge_ctrl.SetBackgroundColour(wx.WHITE)
            gauge_ctrl.SetBorderColor(wx.BLACK)
            gauge_ctrl.SetBorderPadding(1)
        sizer.Add(static_line, 0, wx.EXPAND| wx.ALL, 1)
        sizer.Add(msg_ctrl,0,wx.EXPAND|wx.ALL, 1)
        sizer.Add(gauge_ctrl, 0, wx.EXPAND|wx.ALL, 1)
        sizer.Layout()
        return panel, sizer, static_line, msg_ctrl, gauge_ctrl



class Clipboard:
    class ClipboardTypes(IntEnum):
        DF_BITMAP = 2
        DF_DIB = 8
        DF_DIF = 5
        DF_ENHMETAFILE = 14
        DF_FILENAME = 15
        DF_HTML = 30
        DF_INVALID = 0
        DF_LOCALE = 16
        DF_MAX = 32
        DF_METAFILE = 3
        DF_OEMTEXT = 7
        DF_PALETTE = 9
        DF_PENDATA = 10
        DF_PNG = 31
        DF_PRIVATE = 20
        DF_RIFF = 11
        DF_SYLK = 4
        DF_TEXT = 1
        DF_TIFF = 6
        DF_UNICODETEXT = 13
        DF_WAVE = 12

    @staticmethod
    def write_text(text:str):
        data_obj = wx.TextDataObject()
        data_obj.SetText(text)
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(data_obj)
            wx.TheClipboard.Close()

    @staticmethod
    def read_text()->Optional[str]:
        text_data = wx.TextDataObject()
        if wx.TheClipboard.Open():
            success = wx.TheClipboard.GetData(text_data)
            wx.TheClipboard.Close()
            if success:
                return text_data.GetText()
        return None

    @staticmethod
    def write_html(text:str):
        data_obj = wx.HTMLDataObject()
        data_obj.SetHTML(text)
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(data_obj)
            wx.TheClipboard.Close()

    @staticmethod
    def read_html()->Optional[str]:
        text_data = wx.HTMLDataObject()
        if wx.TheClipboard.Open():
            success = wx.TheClipboard.GetData(text_data)
            wx.TheClipboard.Close()
            if success:
                return text_data.GetHTML()
        return None

    @staticmethod
    def get_type():
        return_list = []
        for t in Clipboard.ClipboardTypes:
            # noinspection PyArgumentList
            if wx.TheClipboard.IsSupported(wx.DataFormat(t)):
                return_list.append(t.name)
        print(return_list)
        return wx.DF_INVALID





"""
    def _set_image_list(self, image_list: ImageList):
        self.image_list = image_list
        self.AssignImageList(self.image_list.image_list, wx.IMAGE_LIST_SMALL)

    def set_col_size(self, col: int, size: int):
        super().get_column_info(col).width = size
        self.SetColumnWidth(col, size)



    def set_columns(self, col_infos: List[Tuple[str, Type, bool]]):
        new_col_info = []
        for c_info in col_infos:
            new_col_info.append((c_info[0], c_info[1], c_info[2], BTFilterType.NONE,None, None))
        super().set_columns(new_col_info)
        self.DeleteAllColumns()
        for i in range(self.GetNumberCols()):
            col_name = self.get_column_info(i).simple_name
            col_width = self.get_column_info(i).width
            if col_width <= 0:
                col_width = wx.LIST_AUTOSIZE_USEHEADER
            self.InsertColumn(i, col_name, width=col_width)



    def load_config(self, config: BasicTableConfig):
        super().load_config(config)
        for i in range(self.GetNumberCols()):
            self.SetColumnWidth(i, self.get_column_info(i).width)

    def update_sort(self):
        super().update_sort()
        for i in range(self.GetNumberRows()):
            self._low_level_set_data(i)

    def save_config(self) ->BasicTableConfig:
        for i in range(self.GetNumberCols()):
            col_width = self.GetColumnWidth(i)
            self.get_column_info(i).width = col_width
        return super().save_config()


    def add_row(self, row_obj: Any, values: List[Any]):
        if len(values) == self.GetNumberCols():
            new_row_index = self.GetNumberRows()
            super().add_row(row_obj, values)
            self.InsertItem(new_row_index, "", -1)
            self._low_level_set_data(new_row_index)
        else:
            mlogger.error(f'{self} add_row ошибка добавления данных, неверное количество столбцов')


    #def insert_row(self, row_obj: Any, values: List[Any]):
    #    if self.GetNumberRows()==0:
    #        self.add_row(values, row_name, row_obj, row_color)
    #        return#
    #
    #    if not 0<=row_index<self.GetNumberRows():
    #        mlogger.error(f'{self} insert_row ошибка добавления данных, неверный индекс положения вставки {row_index}')
    #        return
    #
    #    if len(values)!=self.GetNumberCols():
    #        mlogger.error(f'{self} insert_row ошибка добавления данных, неверное количество столбцов')
    #        return
    #    super().insert_row(values, row_name, row_obj, row_color, row_index)
    #    table_index = self._rows_order.index(row_index)
    #    self.InsertItem(table_index,"",-1)
    #    self._low_level_set_data(row_index)


    def _low_level_set_data(self, row:int):
        list_row = self._rows_order.index(row)
        for i in range(self.GetNumberCols()):
            col_type = self.get_col_type(i)
            if col_type == wx.Bitmap:
                bitmap_name = self.get_value(row, i)
                if bitmap_name is not None:
                    bitmap_index = self.image_list.get_index(bitmap_name)
                    if bitmap_index is not None:
                        self.SetItem(list_row, i, "", bitmap_index)
                    else:
                        self.SetItem(list_row, i, bitmap_name,-1)
            else:
                value = self.get_value(row, i)
                self.SetItem(list_row, i, value, -1)


    def delete_row(self, row: int):
        if 0<= row < self.GetNumberRows():
            table_index = self._rows_order.index(row)
            self.DeleteItem(table_index)
            super().delete_row(row)
        else:
            mlogger.error(f'{self} delete_row неверное значение номера строки для удаления {row}')


    def write_row(self, values: List[Any], row_name: str, row_obj: Any, row_color: Optional[wx.Colour]):
        if len(values) == self.GetNumberCols():
            super().write_row(values, row_name, row_obj, row_color)
            row_index = self.get_row_number_obj(row_obj, False)
            if 0<=row_index<self.GetNumberRows():
                self._low_level_set_data(row_index)
            else:
                mlogger.error(f'{self} write_row ошибка записи данных, неверное значение {row_index}')
        else:
            mlogger.error(f'{self} write_row ошибка добавления данных, неверное количество столбцов')


    def clear(self):
        super().clear()
        self.DeleteAllItems()

    def get_selected_objects(self):
        sel_objects = []
        for i in range(self.GetItemCount()):
            if self.IsSelected(i):
                table_row = self._rows_order[i]
                sel_objects.append(self.get_row_obj(table_row))
        return sel_objects
"""

