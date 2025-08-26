import configparser
from enum import Enum
from typing import List, Any, Optional, Callable, Union, Tuple, Type

import wx

from gui_widgets import ImageList, GuiWidgetSettings, mlogger


class BasicListCtrl(wx.ListCtrl):  # TextEditMixin allows any column to be edited.
    col_count = 0
    _data: List[Any] = []
    _objects: List[Any] = []
    image_list: ImageList
    item_click_callback: Optional[Callable[[Any, bool], None]]
    header_click_callback: Optional[Callable[[Any, int], None]]

    _parent: Any
    _columns: List[Any] = []
    def __init__(self, parent, iid=wx.ID_ANY, pos=wx.DefaultPosition,size=wx.DefaultSize, style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES):
        self._parent = parent
        wx.ListCtrl.__init__(self, parent, iid, pos, size, style)
        self.col_count = 0
        _image_list = ImageList(GuiWidgetSettings.listctrl_bitmap_size)
        self.item_click_callback = None
        self.header_click_callback = None
        self._set_image_list(_image_list)
        self.SetImageList(self.image_list.image_list, wx.IMAGE_LIST_SMALL)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_list_click, self)
        self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._on_list_rclick, self)
        self.Bind(wx.EVT_LIST_COL_CLICK, self._on_header_click, self)
        #self.Bind(wx.EVT_RIGHT_DOWN, self._on_list_rclick, self)
        self._data = []
        self._objects = []


    def set_col_sizes(self, sizes_list: List[int]):
        for col in range(self.GetColumnCount()):
            if len(sizes_list)>col:
                self.SetColumnWidth(col, sizes_list[col])

    def get_col_sizes(self)->List[int]:
        answ = []
        for col in range(self.GetColumnCount()):
            answ.append(self.GetColumnWidth(col))
        return answ


    def _set_image_list(self, image_list: ImageList, img_size: int = wx.IMAGE_LIST_SMALL):
        self.image_list = image_list
        self.SetImageList(self.image_list.image_list, img_size)

    def add_image(self, image_name: Union[str, Enum], image_file_name: str):
        self.image_list.add_from_file_name(image_name, image_file_name)


    def _set_img(self, row_number: int, col_number: int, img_name:Optional[Union[str, Enum]]):
        list_item: wx.ListItem = self.GetItem(row_number, col_number)
        if list_item is not None:
            text = list_item.GetText()
            if img_name is not None:
                index = self.image_list.get_index(img_name)
                if index is not None:
                    self.SetItem(row_number, col_number, text, index)
                else:
                    mlogger.error(f'{self} изображение {img_name} не найдено')
            else:
                self.SetItem(row_number, col_number, text, -1)

    def set_header(self, columns: List[Tuple[str, int, Type]]):
        self.DeleteAllColumns()
        i = 0
        for item in columns:
            col_name = item[0]
            col_width = item[1]
            if col_width<0:
                col_width = wx.LIST_AUTOSIZE_USEHEADER
            self.InsertColumn(i, col_name, width=col_width)
            i+=1
        self.col_count = i
        self._columns = columns

    def get_count(self):
        return len(self._data)

    def add_row(self, data: Union[Tuple, List[Any]], obj: Any):
        if len(data) != self.col_count:
            mlogger.error(f'{self} неверно переданы данные для заполнения')
        else:
            item_index = self.InsertItem(self.GetItemCount(), "", -1)
            self._data.append(data)
            self._objects.append(obj)
            self.update_row(item_index, data, obj)


    def insert_row(self, row_index:int, data: Union[Tuple, List[Any]], obj: Any):
        if len(data) != self.col_count:
            mlogger.error(f'{self} неверно переданы данные для заполнения')
        else:
            item_index = self.InsertItem(row_index, "", -1)
            self._data.insert(row_index, data)  # append(data)
            self._objects.insert(row_index, obj)  # append(obj)
            self.update_row(item_index, data, obj)


    def move_up_row(self, row_index: int):
        if row_index < 0:
            return
        prev_index = row_index - 1
        if prev_index >=0:
            frozen = self.IsFrozen()
            if not frozen:
                self.Freeze()
            prev_obj = self.get_object(prev_index)
            prev_data = self.get_data(prev_index)
            cur_obj = self.get_object(row_index)
            cur_data = self.get_data(row_index)
            self.update_row(prev_index, cur_data, cur_obj)
            self.update_row(row_index, prev_data, prev_obj)
            self.Select(row_index,0)
            self.Select(prev_index)
            if not frozen:
                self.Thaw()


    def move_down_row(self, row_index:int):
        if row_index < 0:
            return
        next_index = row_index + 1
        if next_index < self.GetItemCount():
            frozen = self.IsFrozen()
            if not frozen:
                self.Freeze()
            next_obj = self.get_object(next_index)
            next_data = self.get_data(next_index)
            cur_obj = self.get_object(row_index)
            cur_data = self.get_data(row_index)
            self.update_row(next_index, cur_data ,cur_obj)
            self.update_row(row_index, next_data,next_obj)
            self.Select(row_index, 0)
            self.Select(next_index)
            if not frozen:
                self.Thaw()

    def update_row(self, row_index:int, data: Union[Tuple, List[Any]], obj: Any):
        if len(data) != self.col_count:
            mlogger.error(f'{self} неверно переданы данные для заполнения')

        else:
            for data_index in range(len(data)):
                if data[data_index] is not None:
                    if self._columns[data_index][2] == str:
                        self.SetItem(row_index, data_index, data[data_index])
                    elif self._columns[data_index][2] == wx.Bitmap:
                        self.SetItem(row_index, data_index, '',self.image_list.get_index(data[data_index],True))
                    else:
                        mlogger.error(f'{self} Тип данных {data[data_index]} не может быть добавлен')
                        return
            self._data[row_index] = data
            self._objects[row_index] = obj

    def clear(self):
        self._data.clear()
        self._objects.clear()
        self.DeleteAllItems()

    def delete_row(self, row_number: int):
        if row_number<self.GetItemCount():
            self.DeleteItem(row_number)
            del self._objects[row_number]
            del self._data[row_number]

    def delete_object(self, obj: Any):
        if obj in self._objects:
            self.delete_row(self._objects.index(obj))


    def get_object(self, row_number: int):
        if row_number < self.GetItemCount():
            return self._objects[row_number]
        return None


    def get_object_row(self, obj: Any):
        if obj in self._objects:
            return self._objects.index(obj)

    def get_objects(self):
        return list(self._objects)

    def get_data(self, row_number: int):
        if row_number < self.GetItemCount():
            return self._data[row_number]
        return None

    def get_selected_objects(self)->List[Any]:
        sel_objects = []
        for i in range(self.GetItemCount()):
            if self.IsSelected(i):
                sel_objects.append(self._objects[i])
        return sel_objects

    def get_data_size(self):
        return len(self._data)

    def _on_list_click(self, evt: wx.ListEvent):
        if self.item_click_callback:
            self.item_click_callback(self._objects[evt.GetIndex()], False)

    def _on_list_rclick(self, evt: wx.ListEvent):
        if self.item_click_callback:
            self.item_click_callback(self._objects[evt.GetIndex()], True)
        evt.Skip()

    def _on_header_click(self, evt: wx.ListEvent):
        if self.header_click_callback:
            self.header_click_callback(self._objects[evt.GetIndex()], evt.GetColumn())
        evt.Skip()




