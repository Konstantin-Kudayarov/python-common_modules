import datetime
import locale
import re
from enum import IntEnum, Enum
from typing import Union, Optional, Tuple, Type, List, Any, Dict, Callable

import wx
import wx.grid

from basic import Logger, LogLevel, EventPublisher, XMLStorable
from gui_widgets import (BasicButton, InputOutputPanel, GuiWidgetSettings, _base64_str_to_image, InputBox,
                         BasicCheckList, BasicCheckListWithFilter, BasicCombobox, BasicDateText, PropertiesWindow)


mlogger = Logger(LogLevel.ANY, loger_name='GUI_WIDGETS')

class BTFilterType(IntEnum):
    NONE = 0
    STRING = 1
    FLOAT = 2
    BOOL = 3
    INT = 4
    DATE = 5
    TIME  = 6
    DATETIME = 7
    LIST = 8

    def get_name(self):
        if self == BTFilterType.NONE:
            return 'Нет'
        elif self == BTFilterType.STRING:
            return 'Строка'
        elif self == BTFilterType.BOOL:
            return 'Логическое'
        elif self == BTFilterType.INT:
            return 'Целое'
        elif self == BTFilterType.FLOAT:
            return 'Дробное'
        elif self == BTFilterType.DATE:
            return 'Дата'
        elif self == BTFilterType.TIME:
            return 'Время'
        elif self == BTFilterType.DATETIME:
            return 'Дата и время'
        elif self == BTFilterType.LIST:
            return 'Список'
        return ''

class BTFilterRule(Enum):
    UNKNOWN = 0
    CASE_SENSITIVE = 1
    ENDS_ANY = 2
    CASE_SENSITIVE_ENDS_ANY = 3
    EQUAL = 4
    NOT_EQUAL = 5
    LOWER = 6
    GREATER = 7
    LOWER_OR_EQUAL = 8
    GREATER_OR_EQUAL = 9
    BETWEEN = 10
    BETWEEN_INCLUDE = 11


class BTSortOrder(IntEnum):
    NONE = 0
    ASCENDING = 1
    DESCENDING = 2


class SortFilterPopupWnd(wx.PopupTransientWindow):
    _table_col: int
    _grid: 'BasicGrid'

    _panel: wx.Panel

    # элементы управления сортировкой
    _sort_asc_button:Optional[BasicButton]
    _sort_desc_button:Optional[BasicButton]
    _sort_config_button: Optional[wx.Button]

    # элементы управления фильтрацией
    _input_output_panel: Optional[InputOutputPanel]

    _set_filter_btn: Optional[wx.Button]  # кнопка для выполнения фильтрации
    _clear_filter_btn: Optional[wx.Button]  # кнопка для сброса фильтрации
    _config_filter_btn: Optional[wx.Button]

    _parent: Any
    def __init__(self, parent: 'BasicGrid', table_col: int):
        busy = wx.IsBusy()
        if not busy:
            wx.BeginBusyCursor()
        self._parent = parent
        self._grid = parent
        self._table_col = table_col

        wx.PopupTransientWindow.__init__(self, parent, flags=wx.BORDER_RAISED | wx.PU_CONTAINS_CONTROLS | wx.PD_APP_MODAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self._panel = wx.Panel(self)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key_pressed)
        # элементы управления сортировки
        self._sort_asc_button = None
        self._sort_desc_button = None
        self._sort_config_button = None

        # элементы управления фильтрацией

        self._input_output_panel = None
        self._set_filter_btn = None
        self._clear_filter_btn = None
        self._config_filter_btn = None


        sizer.Add(self._panel, 1, wx.ALL | wx.EXPAND, 5)
        self._main_sizer = wx.BoxSizer(wx.VERTICAL)
        self._panel.SetSizer(self._main_sizer)

        self.SetSizer(sizer)
        self._build_window_elements()



        self.Fit()
        self.Layout()
        if not busy:
            wx.EndBusyCursor()

    def _on_key_pressed(self, event: wx.KeyEvent):

        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Dismiss()
        event.Skip()

    def _build_window_elements(self):
        #can_sort = self._grid.table.get_column_info(self._table_col).can_sort
        #can_filter = BTFilterType.NONE not in self._grid.table.get_column_info(self._table_col).allowed_filters

        if self._grid.table.get_column_info(self._table_col).can_sort:
            self._add_sort_controls()
            self._fill_sort_controls()

        if self._grid.table.get_column_info(self._table_col).can_filter:
            self._add_filter_controls()
            self._fill_filter_controls()

        
        self.SetMinSize(self.GetBestSize())
        self.Layout()
        #self.set_best_size(self._table_col)
        #wx.CallAfter(self.Layout)


    # region Сортировка

    def _add_sort_controls(self):
        self._sort_asc_button = BasicButton(self._panel, label='По возрастанию', style=wx.BORDER_NONE | wx.BU_LEFT)
        self._sort_asc_button.Bind(wx.EVT_BUTTON, self._on_sort_ascending_click)
        self._main_sizer.Add(self._sort_asc_button, 0, wx.EXPAND | wx.ALL, 0)
        self._sort_desc_button = BasicButton(self._panel, label='По убыванию', style=wx.BORDER_NONE | wx.BU_LEFT)
        self._sort_desc_button.Bind(wx.EVT_BUTTON, self._on_sort_descending_click)
        self._main_sizer.Add(self._sort_desc_button, 0, wx.EXPAND | wx.ALL, 0)
        self._sort_config_button = wx.Button(self._panel, label="", size=wx.Size(GuiWidgetSettings.grid_header_icon_size + 8, GuiWidgetSettings.grid_header_icon_size + 8))
        self._sort_config_button.SetBitmap(self._grid.bitmaps['sort_config'])
        self._sort_config_button.Bind(wx.EVT_BUTTON, self._on_sort_config_click)
        self._sort_config_button.SetHelpText("Настроить сортировку")
        self._sort_config_button.SetToolTip("Настроить сортировку")
        self._main_sizer.Add(self._sort_config_button, 0, wx.ALL, 0)

    def _fill_sort_controls(self):
        if self._grid.table.get_column_info(self._table_col).can_sort:
            sort_direction: BTSortOrder = self._grid.table.get_column_info(self._table_col).sort_direction
            if sort_direction == BTSortOrder.ASCENDING:
                self._sort_asc_button.SetBitmap(self._grid.bitmaps['sort_asc_checked'])
                self._sort_desc_button.SetBitmap(self._grid.bitmaps['sort_desc'])
            elif sort_direction == BTSortOrder.DESCENDING:
                self._sort_asc_button.SetBitmap(self._grid.bitmaps['sort_asc'])
                self._sort_desc_button.SetBitmap(self._grid.bitmaps['sort_desc_checked'])
            elif sort_direction == BTSortOrder.NONE:
                self._sort_asc_button.SetBitmap(self._grid.bitmaps['sort_asc'])
                self._sort_desc_button.SetBitmap(self._grid.bitmaps['sort_desc'])

    def _on_sort_ascending_click(self, _evt: wx.CommandEvent):
        if self._grid.table.get_column_info(self._table_col).can_sort:
            for c in range(self._grid.table.GetNumberCols()):
                if self._grid.table.get_column_info(c).can_sort:
                    self._grid.table.get_column_info(c).sort_direction = BTSortOrder.NONE
            self._grid.table.get_column_info(self._table_col).sort_direction = BTSortOrder.ASCENDING

        else:
            return
        self._grid.table.update_sort()
        self.Dismiss()
        self._grid.update_col_header()


    def _on_sort_descending_click(self, _evt: wx.CommandEvent):
        if self._grid.table.get_column_info(self._table_col).can_sort:
            for c in range(self._grid.table.GetNumberCols()):
                if self._grid.table.get_column_info(c).can_sort:
                    self._grid.table.get_column_info(c).sort_direction = BTSortOrder.NONE
            self._grid.table.get_column_info(self._table_col).sort_direction = BTSortOrder.DESCENDING
        else:
            return
        self._grid.table.update_sort()
        self.Dismiss()
        self._grid.update_col_header()


    def _on_sort_config_click(self, _evt: wx.CommandEvent):
        config_sort_dialog = InputBox(self._grid, 'Сортировка', None, None, wx.DefaultPosition, wx.DefaultSize, False, False)

        avail_sort_columns = []
        for i in range(self._grid.GetNumberCols()):
            if self._grid.table.get_column_info(i).can_sort:
                avail_sort_columns.append(i)

        old_sort_order = list(self._grid.table.sort_order)
        avail_values = []
        selected_values = []
        for i in list(old_sort_order):
            avail_values.append(( self._grid.table.get_column_info(i, True).simple_name, i))
            old_sort_order.remove(i)
            if i in avail_sort_columns:
                avail_sort_columns.remove(i)
            if self._grid.table.get_column_info(i, True).sort_direction == BTSortOrder.ASCENDING:
                selected_values.append(i)


        config_sort_dialog.input_panel.add_property('sort_order','',BasicCheckList, False)
        config_sort_dialog.input_panel.set_property('sort_order', selected_values, avail_values)
        #config_sort_dialog.input_panel.set_property_best_size('sort_order')

        config_sort_dialog.Fit()
        config_sort_dialog.CenterOnParent()
        if config_sort_dialog.ShowModal() == wx.ID_OK:
            self._grid.table.sort_order.clear()
            self._grid.table.sort_order.extend(config_sort_dialog.input_panel.get_property('sort_order',True))
            selected_cols = config_sort_dialog.input_panel.get_property('sort_order', False)
            for c in range(self._grid.table.GetNumberCols()):
                if c not in selected_cols:
                    self._grid.table.get_column_info(c, True).sort_direction = BTSortOrder.NONE
                else:
                    self._grid.table.get_column_info(c, True).sort_direction = BTSortOrder.ASCENDING
            self._grid.table.update_sort()
        self.Dismiss()
        self._grid.update_col_header()
        #self.grid.parent_wnd.Raise()

    # endregion

    #region Фильтры

    def _on_filter_control_changed(self, _input_panel: Optional['InputOutputPanel'], prop_name: str):
        have_value = self._get_current_filter_values() is not None

        prop_type = self._grid.table.get_column_info(self._table_col).filter
        if prop_type == BTFilterType.LIST:

            avail_values = self._input_output_panel.get_property('filter_list', True)
            cur_values = self._get_current_filter_values()
            if avail_values and cur_values:
                if len(avail_values) != len(cur_values):
                    have_value = True
                else:
                    have_value = False
        filter_rule: BTFilterRule = self._grid.table.get_column_info(self._table_col).filter_rule
        if prop_name == 'filter_rule':
            filter_rule: BTFilterRule = self._input_output_panel.get_property('filter_rule', False)
            self._grid.table.get_column_info(self._table_col).filter_rule = filter_rule
        elif prop_name in ['filter_case_sensitive','filter_ends_any']:
            case_sensitive = self._input_output_panel.get_property('filter_case_sensitive', False)
            ends_any = self._input_output_panel.get_property('filter_ends_any', False)
            if case_sensitive and ends_any:
                filter_rule = BTFilterRule.CASE_SENSITIVE_ENDS_ANY
            elif case_sensitive and not ends_any:
                filter_rule = BTFilterRule.CASE_SENSITIVE
            elif not case_sensitive and ends_any:
                filter_rule = BTFilterRule.ENDS_ANY
            else:
                filter_rule = BTFilterRule.EQUAL
            self._grid.table.get_column_info(self._table_col).filter_rule = filter_rule

        #if filter_rule is None or filter_rule == BasicTableFilterRule.UNKNOWN:
        #    if not prop_type in [BasicTableFilterType.STRING, BasicTableFilterType.LIST]:
        #        have_value = False

        self._set_filter_btn.Enable(have_value)

        have_filter_value = self._grid.table.get_column_info(self._table_col).filter_value is not None

        if filter_rule in [BTFilterRule.BETWEEN, BTFilterRule.BETWEEN_INCLUDE]:
            self._input_output_panel.show_property('filter_value_2', True, False)
        else:
            self._input_output_panel.show_property('filter_value_2', False, False)
        self._clear_filter_btn.Enable(have_filter_value)
        self.Fit()

    def _on_filter_panel_enter_key_pressed(self, _input_panel: 'InputOutputPanel'):
        self._on_filter_execute(None)

    def _add_filter_controls(self):

        if self._grid.table.get_column_info(self._table_col).can_sort:
            h_line = wx.StaticLine(self._panel, wx.LI_HORIZONTAL)
            self._main_sizer.Add(h_line, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 3)

        if self._grid.table.get_column_info(self._table_col).can_filter:
            self._input_output_panel = InputOutputPanel(self._panel, False, False, border=3)
            self._main_sizer.Add(self._input_output_panel, 0, wx.EXPAND | wx.ALL, 0)
            # фильтры
            filter_type: BTFilterType = self._grid.table.get_column_info(self._table_col).filter
            if filter_type == BTFilterType.STRING:
                self._input_output_panel.add_property('filter_str', '', str, False)
                self._input_output_panel.add_property('filter_case_sensitive', '', bool, False)
                self._input_output_panel.set_property_label_name('filter_case_sensitive', 'Учитывать регистр')
                self._input_output_panel.add_property('filter_ends_any', '', bool, False)
                self._input_output_panel.set_property_label_name('filter_ends_any', 'Любое окончание')
            elif filter_type == BTFilterType.BOOL:
                self._input_output_panel.add_property('filter_bool', '', BasicCombobox, False)
            elif filter_type in [BTFilterType.DATE, BTFilterType.DATETIME, BTFilterType.INT, BTFilterType.FLOAT]:
                self._input_output_panel.add_property('filter_rule', '', BasicCombobox, False)
                if filter_type == BTFilterType.DATE:
                    self._input_output_panel.add_property('filter_value', '', BasicDateText , False)
                    self._input_output_panel.add_property('filter_value_2', '', BasicDateText, False)
                elif filter_type == BTFilterType.INT:
                    self._input_output_panel.add_property('filter_value', '', int, False)
                    self._input_output_panel.add_property('filter_value_2', '', int, False)
                elif filter_type == BTFilterType.FLOAT:
                    self._input_output_panel.add_property('filter_value', '', float, False)
                    self._input_output_panel.add_property('filter_value_2', '', float, False)
            elif filter_type == BTFilterType.LIST:
                self._input_output_panel.add_property('filter_list', '', BasicCheckListWithFilter, False)

            self._input_output_panel.set_focus()
            self._input_output_panel.property_value_changed_callback = self._on_filter_control_changed
            self._input_output_panel.key_enter_pressed_callback = self._on_filter_panel_enter_key_pressed


            h_box_sizer = wx.BoxSizer(wx.HORIZONTAL)
            self._main_sizer.Add(h_box_sizer, 0, wx.EXPAND | wx.ALL, 0)

            self._set_filter_btn = wx.Button(self._panel, label="", size=wx.Size(GuiWidgetSettings.grid_header_icon_size + 8, GuiWidgetSettings.grid_header_icon_size + 8))
            self._set_filter_btn.SetBitmap(self._grid.bitmaps['filter'])
            self._set_filter_btn.SetHelpText("Применить фильтр")
            self._set_filter_btn.SetToolTip("Применить фильтр")
            self._set_filter_btn.Bind(wx.EVT_BUTTON, self._on_filter_execute)
            h_box_sizer.Add(self._set_filter_btn, 0, wx.EXPAND | wx.ALL, 1)

            self._clear_filter_btn = wx.Button(self._panel, label="", size=wx.Size(GuiWidgetSettings.grid_header_icon_size + 8, GuiWidgetSettings.grid_header_icon_size + 8))
            self._clear_filter_btn.SetBitmap(self._grid.bitmaps['filter_clear'])
            self._clear_filter_btn.Bind(wx.EVT_BUTTON, self._on_clear_execute)
            self._clear_filter_btn.SetHelpText("Сбросить фильтр")
            self._clear_filter_btn.SetToolTip("Сбросить фильтр")
            h_box_sizer.Add(self._clear_filter_btn, 0, wx.EXPAND | wx.ALL, 1)

            self._config_filter_btn = wx.Button(self._panel, label="", size=wx.Size(GuiWidgetSettings.grid_header_icon_size + 8, GuiWidgetSettings.grid_header_icon_size + 8))
            self._config_filter_btn.SetBitmap(self._grid.bitmaps['filter_config'])
            self._config_filter_btn.Bind(wx.EVT_BUTTON, self._on_filter_config_execute)
            self._config_filter_btn.SetHelpText("Настроить фильтр")
            self._config_filter_btn.SetToolTip("Настроить фильтр")
            h_box_sizer.Add(self._config_filter_btn, 0, wx.EXPAND | wx.ALL, 1)
            avail_filter_types = self._grid.table.get_column_info(self._table_col).allowed_filters
            if avail_filter_types and len(avail_filter_types)>1:
                self._config_filter_btn.Enable(True)
            else:
                self._config_filter_btn.Enable(False)

            self._on_filter_control_changed(self._input_output_panel, '')

    def _fill_filter_controls(self):
        filter_type: BTFilterType
        filter_values: Any = self._grid.table.get_column_info(self._table_col).filter_value
        filter_type: BTFilterType = self._grid.table.get_column_info(self._table_col).filter
        filter_rule: BTFilterRule = self._grid.table.get_column_info(self._table_col).filter_rule
        if filter_type == BTFilterType.STRING:
            self._input_output_panel.set_property('filter_str', filter_values, None)
            col_width = self._grid.table.get_column_info(self._table_col).width
            ctrl: wx.Control = self._input_output_panel.get_control('filter_str')
            ctrl_width = ctrl.GetBestSize().GetWidth()
            if col_width>ctrl_width:
                ctrl.SetMinSize(wx.Size(int(col_width*0.9),-1))
            if filter_rule == BTFilterRule.CASE_SENSITIVE_ENDS_ANY:
                self._input_output_panel.set_property('filter_case_sensitive', True, None)
                self._input_output_panel.set_property('filter_ends_any', True, None)
            elif filter_rule == BTFilterRule.CASE_SENSITIVE:
                self._input_output_panel.set_property('filter_case_sensitive', True, None)
                self._input_output_panel.set_property('filter_ends_any', False, None)
            elif filter_rule == BTFilterRule.ENDS_ANY:
                self._input_output_panel.set_property('filter_case_sensitive', False, None)
                self._input_output_panel.set_property('filter_ends_any', True, None)
        elif filter_type == BTFilterType.BOOL:
            self._input_output_panel.set_property('filter_bool', filter_values, [('Да', True), ('Нет', False), ('Любое', None)])
        elif filter_type in [BTFilterType.DATE, BTFilterType.DATETIME, BTFilterType.INT, BTFilterType.FLOAT]:
            filter_rules = [('=', BTFilterRule.EQUAL),
                            ('!=', BTFilterRule.NOT_EQUAL),
                            ('>', BTFilterRule.GREATER),
                            ('>=', BTFilterRule.GREATER_OR_EQUAL),
                            ('<', BTFilterRule.LOWER),
                            ('<=', BTFilterRule.LOWER_OR_EQUAL),
                            ('между', BTFilterRule.BETWEEN),
                            ('между (включая)', BTFilterRule.BETWEEN_INCLUDE)]
            if filter_rule not in [BTFilterRule.EQUAL,
                                   BTFilterRule.NOT_EQUAL,
                                   BTFilterRule.GREATER,
                                   BTFilterRule.GREATER_OR_EQUAL,
                                   BTFilterRule.LOWER,
                                   BTFilterRule.LOWER_OR_EQUAL,
                                   BTFilterRule.BETWEEN,
                                   BTFilterRule.BETWEEN_INCLUDE]:
                filter_rule = BTFilterRule.EQUAL
            self._input_output_panel.set_property('filter_rule', filter_rule, filter_rules)
            if filter_rule in [BTFilterRule.BETWEEN, BTFilterRule.BETWEEN_INCLUDE]:
                if type(filter_values) == tuple:
                    self._input_output_panel.set_property('filter_value', filter_values[0], None)
                    self._input_output_panel.set_property('filter_value_2', filter_values[1], None)
            else:
                self._input_output_panel.set_property('filter_value', filter_values, None)
        elif filter_type == BTFilterType.LIST:
            avail_values = []
            avail_names = []
            if filter_values is None:
                filter_values = []
            for row in range(self._grid.GetNumberRows()):
                avail_value = self._grid.table.get_raw_data_value(row, self._table_col, False)
                avail_name = self._grid.table.GetValue(row, self._table_col)
                if avail_value not in avail_values and avail_name not in avail_names:
                    avail_values.append((avail_name, avail_value))
                    avail_names.append(avail_name)
                    if avail_value not in filter_values:
                        filter_values.append(avail_value)



            #avail_values = []
            #avail_names = []
            #rows_order = self._grid.table.get_row_order()
            #need_set_all = False
            #if filter_values is None:
            #    filter_values = []
            #    need_set_all = True
            #for row in range(self._grid.GetNumberRows()):
            #    avail_value = self._grid.table.get_raw_value(rows_order[row], self._table_col)
            #    avail_name = self._grid.table.get_value(rows_order[row], self._table_col)
            #    if avail_name not in avail_names:
            #        avail_names.append(avail_name)
            #        avail_values.append((avail_name, avail_value))
            #    if need_set_all:
            #        if self._grid.IsRowShown(row):
            #            if avail_value not in filter_values:
            #                filter_values.append(avail_value)
            self._input_output_panel.set_property('filter_list', filter_values, avail_values)
            #self._input_output_panel.set_property_best_size('filter_list')
            self.Layout()

        self._on_filter_control_changed(None, '')
        #if self._grid.table.get_column_info(self._table_col).filter_value:
        #    self._config_filter_btn.Show(True)
        #else:
        #    self._config_filter_btn.Show(False)

    def _get_current_filter_values(self):
        filter_type: BTFilterType
        filter_type:BTFilterType = self._grid.table.get_column_info(self._table_col).filter
        filter_val = None
        if filter_type == BTFilterType.STRING:
            filter_val = self._input_output_panel.get_property('filter_str', False)
        elif filter_type == BTFilterType.BOOL:
            filter_val = self._input_output_panel.get_property('filter_bool', False)
        elif filter_type in [BTFilterType.INT, BTFilterType.FLOAT, BTFilterType.DATE, BTFilterType.DATETIME]:
            filter_rule: BTFilterRule = self._input_output_panel.get_property('filter_rule', False)
            if filter_rule not in [BTFilterRule.BETWEEN, BTFilterRule.BETWEEN_INCLUDE]:
                filter_val = self._input_output_panel.get_property('filter_value', False)
            else:
                filter_val = (self._input_output_panel.get_property('filter_value',False), self._input_output_panel.get_property('filter_value_2', False))
        elif filter_type == BTFilterType.LIST:
            filter_val = self._input_output_panel.get_property('filter_list', False)
            filter_avail_val = self._input_output_panel.get_property('filter_list', True)
            # noinspection PyTypeChecker
            filter_ctrl: BasicCheckListWithFilter = self._input_output_panel.get_control('filter_list')
            visible_filter_val = filter_ctrl.get_visible_value()
            if filter_val and filter_avail_val:
                if len(filter_val) == len(filter_avail_val):
                    if len(visible_filter_val) != len(filter_val):
                        filter_val = visible_filter_val
                    else:
                        filter_val = None
        return filter_val

    def _on_filter_execute(self, _evt: Optional[wx.CommandEvent]):
        filter_value = self._get_current_filter_values()
        if filter_value is not None:
            filter_type = self._grid.table.get_column_info(self._table_col).filter
            filter_rule = BTFilterRule.UNKNOWN
            if filter_type == BTFilterType.STRING:
                case_sensitive = self._input_output_panel.get_property('filter_case_sensitive', False)
                ends_any = self._input_output_panel.get_property('filter_ends_any', False)
                if case_sensitive and ends_any:
                    filter_rule = BTFilterRule.CASE_SENSITIVE_ENDS_ANY
                elif case_sensitive and not ends_any:
                    filter_rule = BTFilterRule.CASE_SENSITIVE
                elif not case_sensitive and ends_any:
                    filter_rule = BTFilterRule.ENDS_ANY
                else:
                    filter_rule = BTFilterRule.EQUAL

            elif filter_type == BTFilterType.BOOL:
                filter_rule = BTFilterRule.EQUAL
            elif filter_type in [BTFilterType.INT, BTFilterType.FLOAT, BTFilterType.DATE, BTFilterType.DATETIME]:
                filter_rule = self._input_output_panel.get_property('filter_rule', False)
            elif filter_type == BTFilterType.LIST:
                filter_rule = BTFilterRule.EQUAL
            busy = wx.IsBusy()
            if not busy:
                wx.BeginBusyCursor()
            frozen = self._grid.IsFrozen()
            if not frozen:
                self._grid.Freeze()
            self._grid.ClearSelection()
            self._grid.table.get_column_info(self._table_col).filter = filter_type
            self._grid.table.get_column_info(self._table_col).filter_rule = filter_rule
            self._grid.table.get_column_info(self._table_col).filter_value = filter_value
            self._grid.table.update_filter()
            self._grid.on_filters_changed()

            if not frozen:
                self._grid.Thaw()
            self.Dismiss()
            if not busy:
                wx.EndBusyCursor()
            # noinspection PyProtectedMember


    def _on_clear_execute(self, _evt: wx.CommandEvent):
        self._grid.table.get_column_info(self._table_col).filter_value = None
        self._grid.table.update_filter()
        self._grid.on_filters_changed()
        self.Dismiss()

    def _on_filter_config_execute(self, _evt: wx.CommandEvent):
        available_filter_types: List[BTFilterType] = self._grid.table.get_column_info(self._table_col).allowed_filters
        combo_filter_types: List[Tuple[str, Any]] = [(ft.get_name(), ft) for ft in available_filter_types]
        cur_filter_type = self._grid.table.get_column_info(self._table_col).filter
        if available_filter_types and len(available_filter_types)>1:
            config_sort_dialog = InputBox(self._grid, f'Фильтр столбца: \"{self._grid.table.get_column_info(self._table_col).simple_name}\"', None, None, wx.DefaultPosition, wx.DefaultSize, False, False)
            config_sort_dialog.input_panel.add_property('filter_type', '', BasicCombobox, False)
            config_sort_dialog.input_panel.set_property('filter_type', cur_filter_type, combo_filter_types)
            config_sort_dialog.input_panel.update_view()
            config_sort_dialog.Fit()
            config_sort_dialog.CenterOnParent()
            if config_sort_dialog.ShowModal() == wx.ID_OK:
                filter_type = config_sort_dialog.input_panel.get_property('filter_type',False)
                if filter_type:
                    self._grid.table.get_column_info(self._table_col).filter = filter_type
                    self._grid.table.get_column_info(self._table_col).filter_value = None


            self._grid.table.update_filter()
            self._grid.update_row_sizes()
            self._grid.Refresh()
            self.Dismiss()
            #self.grid.parent_wnd.Raise()

        #endregion



class BasicTableConfig(XMLStorable):

    """Порядок сортировки строк"""
    col_order: List[int]
    row_order: List[int]

    col_size: List[int]
    row_size: List[int]

    sel_row: int
    sel_col: int

    sort_order: List[int]
    sort_config: Dict[int, BTSortOrder]

    filter_rule_config: Dict[int, BTFilterRule]
    filter: Dict[int, BTFilterType]

    can_drag_cols: bool
    can_drag_rows: bool
    can_resize_cols: bool
    can_resize_rows: bool

    row_header_width: int
    col_header_height: int

    row_default_height: int

    def __init__(self):
        XMLStorable.__init__(self)
        self.col_order = []
        self.row_order = []
        self.row_size = []
        self.col_size = []
        self.sel_row = 0
        self.sel_col = 0
        self.sort_order = []
        self.sort_config = {}
        self.filter_rule_config = {}
        self.filter = {}
        self.can_drag_cols = False
        self.can_drag_rows = False
        self.can_resize_cols = False
        self.can_resize_rows = False

        self.col_header_height = 30
        self.row_header_width = 100
        self.row_default_height = 25


class BasicTable(wx.grid.GridTableBase, EventPublisher):
    class CellInfo:
        halign: Optional[int]
        valign: Optional[int]
        background_color: Optional[wx.Colour]
        font: Optional[wx.Font]
        text_color: Optional[wx.Colour]

        def __init__(self):
            self.halign = None
            self.valign = None
            self.background_color = None
            self.font = None
            self.text_color = None


    class ColInfo:
        name: str
        """наименование столбца"""
        type: Type
        """тип столбца"""
        can_sort: bool
        """можно ли сортировать"""
        sort_direction: BTSortOrder
        """выбранный порядок сортировки"""

        allowed_filters: List[BTFilterType]
        """доступные фильтры"""
        filter: BTFilterType
        """текущий выбранный фильтр"""
        filter_rule: BTFilterRule
        """текущее выбранное правило"""
        filter_value: Any
        """текущее значение фильтра"""


        editor: Optional[wx.grid.GridCellEditor]
        renderer: Optional[wx.grid.GridCellRenderer]
        attr: Optional[wx.grid.GridCellAttr]

        width: int
        """ширина столбца"""
    
        @property
        def simple_name(self):
            return self.name.replace('\n',' ').replace('\t',' ').replace('\r','')
        
        @property
        def can_filter(self):
            if BTFilterType.NONE in self.allowed_filters or self.allowed_filters is None:
                return False
            return True

    class RowInfo:
        name: str
        height: int
        color: Optional[wx.Colour]

    grid: Optional['BasicGrid']
    _columns_info: List[ColInfo]
    _col_order: List[int]

    _cell_attr: List[List[CellInfo]]
    _row_info: List[RowInfo]
    _row_order: List[int]
    _row_sorted_order: List[int]
    _row_objects: List[Any]
    _row_raw_data: List[Any]
    _row_grid_data: List[Any]
    _date_format: str
    _time_format: str
    _date_time_format: str
    sort_order: List[int]
    _can_drag_cols: bool
    _can_drag_rows: bool
    _can_resize_cols: bool
    _can_resize_rows: bool


    convert_row_to_grid_data: Optional[Callable[[List],List]]
    def __init__(self):
        # available formats: str, bool, int, float, datetime.date

        wx.grid.GridTableBase.__init__(self)
        EventPublisher.__init__(self)
        self._columns_info = []
        self._col_order = []
        self._cell_attr = []
        self._row_info = []
        self._row_order = []
        self._row_sorted_order = []
        self._row_objects = []
        self._row_raw_data = []
        self._row_grid_data = []
        self._date_format = '%d.%m.%Y'
        self._time_format = '%H:%M'
        self._date_time_format = '%d.%m.%Y %H:%M'
        self.grid = None
        self.sort_order = []
        self._can_drag_rows = False
        self._can_drag_cols = False
        self._can_resize_cols = False
        self._can_resize_rows = False

        self.convert_row_to_grid_data = None


    @property
    def can_drag_rows(self):
        return self._can_drag_rows

    @can_drag_rows.setter
    def can_drag_rows(self, value):
        self._can_drag_rows = value
        self.grid.can_drag_rows = value
        #self.grid.EnableDragRowMove(value)

    @property
    def can_drag_cols(self):
        return self._can_drag_cols

    @can_drag_cols.setter
    def can_drag_cols(self, value):
        self._can_drag_cols = value
        self.grid.can_drag_cols = value
        #self.grid.EnableDragColMove(value)

    @property
    def can_resize_rows(self):
        return self._can_resize_rows

    @can_resize_rows.setter
    def can_resize_rows(self, value):
        self._can_resize_rows = value
        self.grid.EnableDragRowSize(value)

    @property
    def can_resize_cols(self):
        return self._can_resize_cols

    @can_resize_cols.setter
    def can_resize_cols(self, value):
        self._can_resize_cols = value
        self.grid.EnableDragColSize(value)


    @property
    def date_format(self):
        return self._date_format


    @date_format.setter
    def date_format(self, value: str):
        self._date_format = value

    @property
    def time_format(self):
        return self._time_format

    @time_format.setter
    def time_format(self, value: str):
        self._time_format = value

    @property
    def date_time_format(self):
        return self._date_time_format

    @date_time_format.setter
    def date_time_format(self, value: str):
        self._date_time_format = value

    def _convert_grid_val_to_raw(self, grid_row: int, grid_col: int, value: Any):
        old_val = self._row_raw_data[self._row_order[grid_row]][self._col_order[grid_col]]
        if self._columns_info[self._col_order[grid_col]].type == float:
            try:
                return locale.atof(value)
            # noinspection PyB
            except Exception as ex:
                mlogger.error(f'{self} ошибка преобразования {value} для ячейки {grid_col} {grid_row} {ex}')
                return old_val
        return value
    def _convert_row_to_grid(self, row: List[Any])->List[Any]:
        conv_row = []
        if self.convert_row_to_grid_data:
            conv_row.extend(self.convert_row_to_grid_data(row))
        if len(conv_row)==0:
            conv_row.extend(row)

        new_row = []
        for col, row_data in enumerate(conv_row):
            new_row_data = row_data
            if self._columns_info[col].type == datetime.date:
                row_data: datetime.date
                if row_data is not None:
                    try:
                        new_row_data = row_data.strftime(self._date_format)
                    except Exception as ex:
                        mlogger.error(f'{self} ошибка преобразования строки {conv_row} {ex}')
                        new_row_data = None
            elif self._columns_info[col].type == datetime.time:
                row_data: datetime.time
                if row_data is not None:
                    try:
                        new_row_data = row_data.strftime(self._time_format)
                    except Exception as ex:
                        mlogger.error(f'{self} ошибка преобразования строки {conv_row} {ex}')
                        new_row_data = None
            elif self._columns_info[col].type == datetime.datetime:
                row_data: datetime.datetime
                if row_data is not None:
                    try:
                        new_row_data = row_data.strftime(self._date_time_format)
                    except Exception as ex:
                        mlogger.error(f'{self} ошибка преобразования строки {conv_row} {ex}')
                        new_row_data = None
            elif self._columns_info[col].type == int:
                row_data: int
                if row_data is not None:
                    try:
                        new_row_data = locale.str(row_data)
                    except Exception as ex:
                        mlogger.error(f'{self} ошибка преобразования строки {conv_row} {ex}')
                        new_row_data = None
            elif self._columns_info[col].type == float:
                row_data: float
                if row_data is not None:
                    try:
                        new_row_data = locale.str(row_data)
                    except Exception as ex:
                        mlogger.error(f'{self} ошибка преобразования строки {conv_row} {ex}')
                        new_row_data = None
            new_row.append(new_row_data)
        return new_row


    def add_row(self, obj: Any, row: Union[List[Any], Tuple], update_grid: bool = True):
        """Добавление одной строки"""
        if not obj in self._row_objects:
            self._row_objects.append(obj)
            self._row_raw_data.append(row)
            self._row_grid_data.append(self._convert_row_to_grid(row))
            cell_attr_row = []
            for i in range(len(row)):
                new_cell_info = self.CellInfo()
                cell_attr_row.append(new_cell_info)
            self._cell_attr.append(cell_attr_row)
            r_info = BasicTable.RowInfo()
            r_info.name = str(len(self._row_objects))
            r_info.height = self.grid.GetDefaultRowSize()
            r_info.color = None
            self._row_info.append(r_info)
            self._row_order.append(len(self._row_objects)-1)
            self._row_sorted_order.append(len(self._row_objects)-1)
            if update_grid:
                self.grid.update_view()
                self.update_sort()
                self.update_filter()
                self.grid.update_row_sizes()
            return True
        return False


    def add_multiple_rows(self, rows: List[Tuple[Any, Union[List[Any], Tuple]]]):
        """Добавление нескольких строк"""
        for r_obj, r_items in rows:
            self.add_row(r_obj, r_items, False)
        self.grid.update_view()
        self.update_sort()
        self.update_filter()


    def delete_row(self, obj: Any, update_grid: bool = True):
        """Удаление одной строки"""
        if obj in self._row_objects:
            r_index = self._row_objects.index(obj)
            #o_index = -1
            del self._row_objects[r_index]
            del self._row_info[r_index]
            del self._row_raw_data[r_index]
            del self._row_grid_data[r_index]
            del self._cell_attr[r_index]
            if r_index in self._row_order:
                self._row_order.remove(r_index)
            if r_index in self._row_sorted_order:
                self._row_sorted_order.remove(r_index)

            for i, r in enumerate(list(self._row_order)):
                if r>r_index:
                    self._row_order[i] -= 1

            for i, r in enumerate(list(self._row_sorted_order)):
                if r>r_index:
                    self._row_sorted_order[i] -= 1


            if update_grid:
                self.grid.update_view()
                self.update_sort()
                self.update_filter()
            return True
        return False

    def delete_multiple_rows(self, objs: List[Any]):
        """Удаление нескольких строк"""
        r_index_list = []
        for obj in objs:
            if obj in self._row_objects:
                r_index_list.append(self._row_objects.index(obj))
        for obj in objs:
            self.delete_row(obj,False)
        self.grid.update_view()
        self.update_sort()
        self.update_filter()


    def write_row(self,obj: Any, row: Union[List[Any], Tuple], update_grid: bool = True):
        """Запись одной строки"""
        if obj in self._row_objects:
            r_index = self._row_objects.index(obj)
            self._row_raw_data[r_index] = row
            self._row_grid_data[r_index] = self._convert_row_to_grid(row)
            if update_grid:
                self.grid.update_view()
                self.update_sort()
                self.update_filter()

    def clear_rows(self):
        self._row_objects.clear()
        self._row_sorted_order.clear()
        self._row_info.clear()
        self._row_raw_data.clear()
        self._row_grid_data.clear()
        self._cell_attr.clear()
        self.grid.update_view()
        self.update_sort()
        self.update_filter()


    def write_multiple_rows(self, rows: List[Tuple[Any, Union[List[Any], Tuple]]]):
        """Запись нескольких строк"""
        for r_obj, row in rows:
            self.write_row(r_obj, row, False)
        self.grid.update_view()
        self.update_sort()
        self.update_filter()


    #def get_raw_value(self, table_row:int, table_col: int):
    #    return self._row_raw_data[self._row_order[table_row]][self._col_order[table_col]]


    def get_raw_row(self, obj: Any):
        """получить """
        if obj in self._row_objects:
            r_index = self._row_objects.index(obj)
            return self._row_raw_data[r_index]
        return None

    def get_col_index(self, grid_col: int):
        return self._col_order[grid_col]

    def get_row_index(self, obj: Any):
        """возвращает номер строки которая просто по порядку в табилце для объекта"""
        if obj in self._row_objects:
            return self._row_objects.index(obj)
        return None

    def set_grid(self, grid: 'BasicGrid'):
        self.grid = grid


    def set_columns(self, columns: List[Tuple[str, Type, bool, Union[BTFilterType, List[BTFilterType]], Optional[wx.grid.GridCellRenderer], Optional[wx.grid.GridCellEditor]]]):
        self._columns_info.clear()
        self._col_order.clear()
        for i in range(len(columns)):
            self._col_order.append(i)
        wx.CallAfter(self.on_col_order_changed)

        for i,col_data in enumerate(columns):
            new_col = BasicTable.ColInfo()
            new_col.name = col_data[0]
            new_col.type = col_data[1]
            new_col.can_sort = col_data[2]
            new_col.sort_direction = BTSortOrder.NONE
            new_col.width = self.grid.GetDefaultColSize()
            if type(col_data[3])==BTFilterType:
                new_col.allowed_filters = [col_data[3]]
            else:
                new_col.allowed_filters = col_data[3]

            new_col.filter = new_col.allowed_filters[0]
            new_col.filter_rule = BTFilterRule.UNKNOWN
            new_col.filter_value = None

            new_col.renderer = col_data[4]
            new_col.editor = col_data[5]
            self._columns_info.append(new_col)

        self.sort_order.clear()
        for i, col_data in enumerate(self._columns_info):
            if col_data.can_sort:
                self.sort_order.append(i)
        self.grid.update_view()


    def load_config(self, config: BasicTableConfig):
        if self.GetNumberRows() == len(config.row_order) == len(config.row_size):
            self._row_order.clear()
            self._row_order.extend(config.row_order)
            self._row_sorted_order.clear()
            self._row_sorted_order.extend(config.row_order)


            for i, r_size in enumerate(config.row_size):
                self.get_row_info(i).height = r_size
            wx.CallAfter(self.on_row_order_changed)
        if self.GetNumberCols() == len(config.col_order) == len(config.col_size):
            self._col_order.clear()
            self._col_order.extend(config.col_order)
            for i, r_size in enumerate(config.col_size):
                self.get_column_info(i).width = r_size
            if len(config.sort_order)>0:
                self.sort_order.clear()
                self.sort_order.extend(config.sort_order)
            wx.CallAfter(self.on_col_order_changed)
        self.grid.update_view()
        self.grid.update_row_sizes()
        self.grid.update_col_sizes()
        if config.sel_row<self.GetNumberRows() and config.sel_col<self.GetNumberCols():
            sel_coord = wx.grid.GridCellCoords(config.sel_row, config.sel_col)
            self.grid.GoToCell(sel_coord)
            self.grid.MakeCellVisible(sel_coord)
        if self.GetNumberCols() == len(config.col_order) == len(config.col_size):
            for c in range(self.GetNumberCols()):
                self.get_column_info(c).sort_direction = config.sort_config[c]
            self.update_sort()

        if self.GetNumberCols() == len(config.filter_rule_config):
            for c in range(self.GetNumberCols()):
                self.get_column_info(c).filter_rule = config.filter_rule_config[c]
            self.update_filter()

        if self.GetNumberCols() == len(config.filter):
            for c in range(self.GetNumberCols()):
                if config.filter[c] in self.get_column_info(c).allowed_filters:
                    self.get_column_info(c).filter = config.filter[c]
                else:
                    self.get_column_info(c).filter = self.get_column_info(c).allowed_filters[0]
            self.update_filter()
        self.can_resize_rows = config.can_resize_rows
        self.can_resize_cols = config.can_resize_cols
        self.can_drag_rows = config.can_drag_rows
        self.can_drag_cols = config.can_drag_cols
        if config.col_header_height:
            self.grid.SetColLabelSize(config.col_header_height)

        if config.row_header_width:
            self.grid.SetRowLabelSize(config.row_header_width)

        if config.row_default_height:
            self.grid.SetDefaultRowSize(config.row_default_height)


    def save_config(self)->BasicTableConfig:
        self.clear_filter()
        config = BasicTableConfig()
        config.row_size.clear()
        config.row_order = list(self._row_order)

        for r in range(self.GetNumberRows()):
            config.row_size.append(self.get_row_info(r).height)


        config.col_order = list(self._col_order)
        config.col_size.clear()
        for r in range(self.GetNumberCols()):
            config.col_size.append(self.get_column_info(r).width)
        config.sel_col = self.grid.GetGridCursorCol()
        config.sel_row = self.grid.GetGridCursorRow()
        config.sort_order.clear()
        config.sort_order.extend(self.sort_order)

        for c in range(self.GetNumberCols()):
            config.sort_config[c] = self.get_column_info(c).sort_direction

        for c in range(self.GetNumberCols()):
            config.filter_rule_config[c] = self.get_column_info(c).filter_rule

        for c in range(self.GetNumberCols()):
            config.filter[c] = self.get_column_info(c).filter

        config.can_resize_rows = self.can_resize_rows
        config.can_resize_cols = self.can_resize_cols
        config.can_drag_rows = self.can_drag_rows
        config.can_drag_cols = self.can_drag_cols

        config.col_header_height = self.grid.GetColLabelSize()
        config.row_header_width = self.grid.GetRowLabelSize()
        config.row_default_height = self.grid.GetDefaultRowSize()


        return config


    def get_selected_objects(self):
        selected_rows = self.grid.get_selected_grid_rows()
        answer = []
        for r in selected_rows:
            answer.append(self._row_objects[self._row_order[r]])
        return answer

    def get_object(self, grid_row: int, table_row: bool=False):
        if not table_row:
            if 0<=grid_row< len(self._row_order):
                return self._row_objects[self._row_order[grid_row]]
            else:
                return None
        else:
            return self._row_objects[grid_row]

    def get_objects(self):
        return list(self._row_objects)

    def get_total_rows_count(self):
        """количество неотфильтрованных объектов"""
        return len(self._row_sorted_order)

    def goto_object(self, obj: Any, grid_col: int):
        if obj in self._row_objects:
            table_index = self._row_objects.index(obj)
            if table_index in self._row_order:
                grid_row = self._row_order.index(table_index)
                coords = wx.grid.GridCellCoords(grid_row, grid_col)

                if coords.GetRow()<0:
                    coords.SetRow(0)

                if coords.GetCol()<0:
                    coords.SetCol(0)

                self.grid.GoToCell(coords)
                self.grid.SetGridCursor(coords)
                self.grid.MakeCellVisible(coords)


    # region Сортировка
    def _make_sort(self):
        sort_order = []
        # sort_order - столбцы grid
        type_replacement: Dict[type, Any] = {str: '',
                                             datetime.date: datetime.date.min,
                                             datetime.datetime: datetime.datetime.min,
                                             int: 0,
                                             float: 0.0,
                                             bool: False}

        for c in self.sort_order:
            if self.get_column_info(c, True).can_sort and self.get_column_info(c, True).sort_direction != BTSortOrder.NONE:
                reverse = False
                if self.get_column_info(c, True).sort_direction == BTSortOrder.DESCENDING:
                    reverse = True
                if self.get_column_info(c, True).type == bool:
                    reverse = not reverse
                if self.get_column_info(c, True).type in type_replacement.keys():
                    sort_order.append((c, reverse,type_replacement[self.get_column_info(c, True).type]))
                else:
                    sort_order.append((c, reverse, type_replacement[self.get_column_info(c, True).type]))

        if sort_order:
            tmp_list = [(self._row_raw_data[i], i) for i in range(len(self._row_raw_data))]
            if tmp_list:
                for key, reverse, repl1 in reversed(sort_order):
                    if repl1:
                        tmp_list.sort(key=lambda x: x[0][key] or repl1, reverse=reverse)
                    else:
                        tmp_list.sort(key=lambda x: x[0][key], reverse=reverse)
                sorted_l, permutation = zip(*tmp_list)
                return permutation
        return None

    def update_sort(self):
        """Обновление сортировки"""
        frozen = self.grid.IsFrozen()
        if not frozen:
            self.grid.Freeze()
        busy = wx.IsBusy()
        if not busy:
            wx.BeginBusyCursor()

        permutations = self._make_sort()
        if permutations:
            self._row_sorted_order.clear()
            self._row_sorted_order.extend(permutations)
            tmp_list = list(self._row_order)
            self._row_order.clear()
            for i in self._row_sorted_order:
                if i in tmp_list:
                    self._row_order.append(i)
            self.grid.update_view()
            self.grid.update_row_sizes()
            self.grid.update_row_header()
            wx.CallAfter(self.on_row_order_changed)
        #else:
        #    self._row_sorted_order.clear()
        #    for i in range(len(self._row_objects)):
        #        self._row_sorted_order.append(i)
        #    tmp_list = list(self._row_order)
        #    self._row_order.clear()
        #    for i in self._row_sorted_order:
        #        if i in tmp_list:
        #            self._row_order.append(i)
        #    self.grid.update_view()
        #    self.grid.update_row_sizes()
        #    self.grid.update_row_header()

        if not busy:
            wx.EndBusyCursor()
        if not frozen:
            self.grid.Thaw()
    # endregion

    # region Фильтр
    def update_filter(self):
        """Обновление фильтров"""
        frozen = self.grid.IsFrozen()
        if not frozen:
            self.grid.Freeze()
        busy = wx.IsBusy()
        if not busy:
            wx.BeginBusyCursor()

        self._row_order.clear()
        for row_index in self._row_sorted_order:
            if self._is_row_visible(row_index):
                self._row_order.append(row_index)
        self.grid.update_view()
        self.grid.update_row_sizes()
        self.grid.update_row_header()

        if not busy:
            wx.EndBusyCursor()
        if not frozen:
            self.grid.Thaw()

    def show_row_obj(self, obj: Any, show: bool):
        index = self.get_row_index(obj)
        if show:
            old_order = list(self._row_order)
            self._row_order.clear()

            for i in self._row_sorted_order:
                if i == index or i in old_order:
                    self._row_order.append(i)
            self.grid.update_view()
            self.grid.update_row_sizes()
            self.grid.update_row_header()
        else:
            if index in self._row_order:
                self._row_order.remove(index)
            self.grid.update_view()
            self.grid.update_row_sizes()
            self.grid.update_row_header()





    def clear_filter(self):
        for col in self._col_order:
            self.get_column_info(col).filter_value = None
        self.update_filter()


    def _is_row_visible(self, row: int):
        is_visible = True
        for col in range(self.GetNumberCols()):
            filter_rule: BTFilterRule = self.get_column_info(col).filter_rule
            filter_type: BTFilterType = self.get_column_info(col).filter
            filter_value: Any = self.get_column_info(col).filter_value


            if filter_value is None:
                continue
            data = self._row_raw_data[row][self._col_order[col]]
            if filter_type == BTFilterType.STRING:
                f_val = re.escape(filter_value)
                f_val = f_val.replace('\\*', '.*?')
                f_val = f_val.replace('\\?', '.')
                flag = re.NOFLAG
                if not filter_rule in [BTFilterRule.CASE_SENSITIVE, BTFilterRule.CASE_SENSITIVE_ENDS_ANY]:
                    flag = re.IGNORECASE
                if filter_rule in [BTFilterRule.ENDS_ANY, BTFilterRule.CASE_SENSITIVE_ENDS_ANY]:
                    f_val.rstrip('.*?')
                    f_val = f_val+'.*?'
                cur_found = False
                for l in data.split('\n'):
                    result = re.match(f'^{f_val}$', l, flags=flag)
                    if result:
                        cur_found = True
                if not cur_found:
                    is_visible = False
            elif filter_type == BTFilterType.BOOL:
                if filter_rule ==BTFilterRule.EQUAL:
                    if not data == filter_value and filter_value is not None:
                        is_visible = False
            elif filter_type in [BTFilterType.DATE, BTFilterType.DATETIME, BTFilterType.INT, BTFilterType.FLOAT]:

                if filter_rule ==BTFilterRule.EQUAL:
                    if not data == filter_value:
                        is_visible = False
                elif filter_rule == BTFilterRule.NOT_EQUAL:
                    if not data != filter_value:
                        is_visible = False

                elif filter_rule == BTFilterRule.LOWER:
                    if data is None or not data < filter_value:
                        is_visible = False
                elif filter_rule == BTFilterRule.LOWER_OR_EQUAL:
                    if data is None or not data <= filter_value:
                        is_visible = False
                elif filter_rule == BTFilterRule.GREATER:
                    if data is None or not data > filter_value:
                        is_visible = False
                elif filter_rule == BTFilterRule.GREATER_OR_EQUAL:
                    if data is None or not data >= filter_value:
                        is_visible = False
                elif filter_rule == BTFilterRule.BETWEEN:
                    if data is None or not filter_value[0]< data < filter_value[1]:
                        is_visible = False
                elif filter_rule == BTFilterRule.BETWEEN_INCLUDE:
                    if data is None or not filter_value[0]<= data <= filter_value[1]:
                        is_visible = False
            elif filter_type == BTFilterType.LIST:
                if data not in filter_value:
                    is_visible = False

        #row_visible = self.get_row_visible(row)
        #if not row_visible:
        #    is_visible = False

        return is_visible

    # endregion

    def set_rows_order(self, row_order: List[int]):
        if len(row_order) <= self.get_total_rows_count():
            self._row_order.clear()
            self._row_order.extend(row_order)

    def set_rows_sort_order(self, row_order: List[int]):
        if len(set(row_order)) == self.get_total_rows_count():
            self._row_sorted_order.clear()
            self._row_sorted_order.extend(row_order)


    def get_rows_order(self):
        return list(self._row_order)

    def get_rows_sort_order(self):
        return list(self._row_sorted_order)

    def set_columns_order(self, col_order: List[int]):
        self._col_order.clear()
        self._col_order.extend(col_order)

    def get_columns_order(self):
        return list(self._col_order)

    def move_row(self, grid_old_row_pos: int, grid_new_row_pos: int):
        if 0<=grid_old_row_pos<len(self._row_order) and 0<=grid_new_row_pos<len(self._row_order):
            old_val = self._row_order[grid_old_row_pos]
            new_val = self._row_order[grid_new_row_pos]
            self._row_sorted_order.insert(self._row_sorted_order.index(new_val), self._row_sorted_order.pop(self._row_sorted_order.index(old_val)))
        if 0<=grid_old_row_pos<len(self._row_order):
            self._row_order.insert(grid_new_row_pos, self._row_order.pop(grid_old_row_pos))
        self.on_row_order_changed()

    def on_col_order_changed(self):
        """событие когда изменяется порядок одной или нескольких строк"""
        for c in self._columns_info:
            print(c.name,end='')
        print('')
        print(self)
        raise NotImplementedError

    def on_row_order_changed(self):
        """событие когда изменяется порядок одной или нескольких строк"""

        for c in self._columns_info:
            print(c.name,end='')
        print('')
        print(self)
        raise NotImplementedError


    def get_column_info(self, grid_column: int, table_col: bool=False):
        if not table_col:
            return self._columns_info[self._col_order[grid_column]]
        else:
            return self._columns_info[grid_column]

    def get_row_info(self, grid_row: int, table_row: bool=False):
        if not table_row:
            try:
                return self._row_info[self._row_order[grid_row]]
            except Exception as ex:
                mlogger.error(f'{self} Ошибка чтения значения {grid_row} {table_row} {ex}')
                return None
        else:
            try:
                return self._row_info[grid_row]
            except Exception as ex:
                mlogger.error(f'{self} Ошибка чтения значения {grid_row} {table_row} {ex}')
                return None


    def get_cell_attribute(self, grid_row: int, grid_col: int, table_coord: bool = False):
        try:
            if not table_coord:
                return self._cell_attr[self._row_order[grid_row]][self._col_order[grid_col]]
            else:
                return self._cell_attr[grid_row][grid_col]
        except Exception as ex:
            mlogger.error(f'{self} Ошибка чтения значения {grid_row} {grid_col} {ex}')
            return None



   # region Наследуемые функции

    def GetNumberCols(self):
        return len(self._col_order)

    def GetNumberRows(self):
        return len(self._row_order)

    def GetColLabelValue(self, grid_col: int):
        """ Наименование столбца """
        if 0<=grid_col < len(self._col_order):
            return self._columns_info[self._col_order[grid_col]].name
        return ''

    def GetRowLabelValue(self, grid_row: int):
        if 0<=grid_row < len(self._row_order):
            return self._row_info[self._row_order[grid_row]].name
        return ''


    def get_raw_data_value(self, grid_row: int, grid_col:int, table_coords: bool):
        if not table_coords:
            return self._row_raw_data[self._row_order[grid_row]][self._col_order[grid_col]]
        else:
            return self._row_raw_data[grid_row][grid_col]

    def GetValue(self, grid_row:int, grid_col:int):
        return self._row_grid_data[self._row_order[grid_row]][self._col_order[grid_col]]

    def SetValue(self, grid_row: int, grid_col: int, value):
        old_val = self._row_raw_data[self._row_order[grid_row]][self._col_order[grid_col]]
        self._row_raw_data[self._row_order[grid_row]][self._col_order[grid_col]] =  self._convert_grid_val_to_raw(grid_row, grid_col, value)
        if old_val != self._row_raw_data[self._row_order[grid_row]][self._col_order[grid_col]]:
            self._row_grid_data[self._row_order[grid_row]][self._col_order[grid_col]] = value

    def IsEmptyCell(self, grid_row: int, grid_col: int):
        """ Является ли ячейка пустой"""
        return self._row_grid_data[self._row_order[grid_row]][self._col_order[grid_col]] is None

    def GetTypeName(self, grid_row: int, grid_col: int):
        """ Получить тип значения в ячейке """
        if 0<=grid_col<self.GetNumberCols():
            if self._columns_info[self._col_order[grid_col]].type == bool:
                return wx.grid.GRID_VALUE_BOOL
            #elif self._columns_info[self._col_order[grid_col]].type == datetime.date:
            #    return wx.grid.GRID_VALUE_DATE
            #elif self._columns_info[self._col_order[grid_col]].type == datetime.time:
            #    return wx.grid.GRID_VALUE_DATETIME
            #elif self._columns_info[self._col_order[grid_col]].type == datetime.datetime:
            #    return wx.grid.GRID_VALUE_DATETIME
            #elif self._columns_info[self._col_order[grid_col]].type == int:
            #    return wx.grid.GRID_VALUE_NUMBER
            #elif self._columns_info[self._col_order[grid_col]].type == float:
            #    return wx.grid.GRID_VALUE_FLOAT
        return wx.grid.GRID_VALUE_TEXT

    def CanGetValueAs(self, grid_row: int, grid_col: int, type_name: str):
        """ Является ли значение в ячейке заданного типа """
        # функция необходима для определения типа рендера который занимается отображением ячейки
        # рендеры Grid не устраивают, поэтому будем использовать стандарный для отображения текста
        if type_name == self.GetTypeName(grid_row, grid_col):
            return True
        return False


    def GetAttr(self, grid_row:int, grid_col:int, kind):
        attr: wx.grid.GridCellAttr = wx.grid.GridCellAttr() #wx.grid.GridTableBase.GetAttr(self, row, col, kind)  # wx.grid.GridCellAttr()

        cell_info: BasicTable.CellInfo = self.get_cell_attribute(grid_row, grid_col)
        if cell_info:
            halign = cell_info.halign
            valign = cell_info.valign
            if halign is None:
                halign = wx.ALIGN_LEFT
            if valign is None:
                valign = wx.ALIGN_TOP
            attr.SetAlignment(halign, valign)

        if cell_info and cell_info.background_color:
            attr.SetBackgroundColour(cell_info.background_color)
        elif cell_info and cell_info.background_color is None:
            if self.get_row_info(grid_row).color:
                attr.SetBackgroundColour(self.get_row_info(grid_row).color)
        if cell_info is not None:
            if cell_info.font is not None:
                attr.SetFont(cell_info.font)
            if cell_info.text_color is not None:
                attr.SetTextColour(cell_info.text_color)

        col_info: BasicTable.ColInfo = self.get_column_info(grid_col)
        if col_info is not None:

            if col_info.renderer:
                attr.SetRenderer(col_info.renderer)
            if col_info.editor:
                attr.SetRenderer(col_info.editor)




        #t_attr = self._cell_attributes[table_row][table_col]
        #if self._col_info[table_col].col_editor_instance is not None:
        #    #self._col_info[table_col].col_editor_instance.IncRef()
        #    try:
        #        attr.SetEditor(self._col_info[table_col].col_editor_instance)
        #    except Exception as ex:
        #        mlogger.error(f'{self} Ошибка SetEditor для объекта {self} {ex}')
        #
        #h_align = 0
        #v_align = 0
        #
        #if self.default_cell_alignment is not None:
        #    h_align = self.CellAttributes.h_align(self.default_cell_alignment)
        #    v_align = self.CellAttributes.v_align(self.default_cell_alignment)
        #    attr.SetAlignment(h_align, v_align)
        #
        #if self._default_cell_font:
        #    attr.SetFont(self._default_cell_font)
        #
        #if t_attr.have_value or self._col_info[table_col].read_only:
        #    if t_attr.readonly is not None:
        #        attr.SetReadOnly(t_attr.readonly)
        #    if self._col_info[table_col].read_only:
        #        attr.SetReadOnly(True)
        #    if t_attr.background_color is not None:
        #        attr.SetBackgroundColour(t_attr.background_color)
        #    if t_attr.text_color is not None:
        #        attr.SetTextColour(t_attr.text_color)
        #
        #    if t_attr.align is not None:
        #        h_align = self.CellAttributes.h_align(t_attr.align)
        #    if t_attr.align is not None:
        #        v_align = self.CellAttributes.v_align(t_attr.align)
        #    attr.SetAlignment(h_align, v_align)
        #    if t_attr.font:
        #        attr.SetFont(t_attr.font)
        #    else:
        #        if self._default_cell_font:
        #            attr.SetFont(self._default_cell_font)
        #attr.IncRef()
        return attr

    # endregion

class BasicGridDropTarget(wx.DropTarget):
    _grid_ctrl: 'BasicGrid'

    _last_scroll_time: datetime.datetime

    _textdo: wx.TextDataObject  # DF_TEXT , DF_UNICODETEXT
    _imagedo: wx.ImageDataObject  # DF_PNG
    _htmldo: wx.HTMLDataObject  # DF_HTML
    _filedo: wx.FileDataObject  # DF_FILENAME
    _bmpdo: wx.BitmapDataObject  # DF_BITMAP
    _recv_data: Any

    def __init__(self, gridctrl: 'BasicGrid'):
        wx.DropTarget.__init__(self)
        self._last_scroll_time = datetime.datetime.now()
        # WxEvents.__init__(self)
        self._grid_ctrl = gridctrl
        # wx.DF_INVALID
        # wx.DF_TEXT
        # wx.DF_BITMAP
        # wx.DF_METAFILE
        # wx.DF_UNICODETEXT
        # wx.DF_FILENAME
        # wx.DF_HTML
        # wx.DF_PNG
        self._do = wx.DataObjectComposite()
        self._textdo = wx.TextDataObject()  # DF_TEXT , DF_UNICODETEXT
        self._imagedo = wx.ImageDataObject()  # DF_PNG
        self._htmldo = wx.HTMLDataObject()  # DF_HTML
        self._filedo = wx.FileDataObject()  # DF_FILENAME
        self._bmpdo = wx.BitmapDataObject()  # DF_BITMAP
        self._recv_data = None

        # self._do.Add(self._urldo)
        self._do.Add(self._textdo)
        self._do.Add(self._imagedo)
        self._do.Add(self._htmldo)
        self._do.Add(self._filedo)
        self._do.Add(self._bmpdo)
        self.SetDataObject(self._do)


    def get_grid_cell(self, x, y):
        grid_mouse_pos: wx.Point  = self._grid_ctrl.CalcUnscrolledPosition(wx.Point(x, y))
        row = self._grid_ctrl.YToRow(grid_mouse_pos.Get()[1])
        col = self._grid_ctrl.XToCol(grid_mouse_pos.Get()[0])
        if row>=0 and col>=0:
            return wx.grid.GridCellCoords(row, col)
        return None

    def select_grid_item(self, grid_coords: wx.grid.GridCellCoords):
        if grid_coords is not None:
            selection_mode = self._grid_ctrl.GetSelectionMode()
            if selection_mode == wx.grid.Grid.GridSelectRows:
                self._grid_ctrl.SetFocus()
                self._grid_ctrl.SelectRow(grid_coords.GetRow())
            else:
                self._grid_ctrl.GoToCell(grid_coords)
                self._grid_ctrl.SetFocus()
                self._grid_ctrl.SelectBlock(grid_coords.GetRow(), grid_coords.GetCol(), grid_coords.GetRow(), grid_coords.GetCol())


    def OnData(self, x, y, def_result):
        """при получении данных после отпускания мыши, def_result = то действие которое просит выполнить пользователь"""
        data_result = def_result
        grid_coords = self.get_grid_cell(x,y)
        if grid_coords is not None:
            if self._grid_ctrl.can_drop_to_cell_data:
                if not self._grid_ctrl.can_drop_to_cell_data(grid_coords, self._recv_data):
                   data_result = wx.DragNone
                else:
                    if self._grid_ctrl.drop_to_cell_execute:
                        wx.CallAfter(self._grid_ctrl.drop_to_cell_execute, grid_coords, self._recv_data, def_result)
        else:
            data_result = wx.DragNone
        self._recv_data = None
        return data_result


    def OnDrop(self, x, y):  # real signature unknown; restored from __doc__
        """при отпускании мыши с данными вызывается один раз"""
        recv_raw_data = None

        if self.GetData():
            rf: wx.DataFormat = self._do.GetReceivedFormat()
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
        grid_cell = self.get_grid_cell(x,y)
        if grid_cell is not None:
            if self._grid_ctrl.can_drop_to_cell_data:
                drag_complete_result = self._grid_ctrl.can_drop_to_cell_data(grid_cell, recv_raw_data)
                if drag_complete_result:
                    self._recv_data = recv_raw_data
        return drag_complete_result

    def OnDragOver(self, x, y, def_result):
        """при попадании мыши на окно с перетаскиваемыми данными постоянно по координатам"""
        # return wx.DragError  # вызывает ошибку - возвращать нельзя
        # return wx.DragCancel  # вызывает ошибку это какая-то внутренняя фигня - возвращать нельзя
        # return wx.DragNone  1# показывает, что файл перенести нелья и OnDropFiles Не вызывается
        # return wx.DragCopy  2# показывает плюс и картинку копирования
        # return wx.DragMove 3 # показывает картинку перемещния и говорит перемещение
        # return wx.DragLink 4 # показывает картинку перемещния и говорит перемещение
        drag_result = def_result
        grid_coords = self.get_grid_cell(x,y)
        if self._grid_ctrl.can_drop_to_cell and grid_coords is not None:
            if not self._grid_ctrl.can_drop_to_cell(grid_coords):
                drag_result = wx.DragNone
        else:
            drag_result = wx.DragNone
        self._scroll_grid(x, y)
        if drag_result != wx.DragNone:
            self.select_grid_item(grid_coords)
        return drag_result

    def OnEnter(self, x, y, def_result):  # real signature unknown; restored from __doc__
        """при заведении объекта в окно вызывается один раз"""
        self._grid_ctrl.SetFocus()
        drag_result = def_result
        return drag_result

    def OnLeave(self):  # real signature unknown; restored from __doc__
        self._grid_ctrl.SetFocus()

    def _scroll_grid(self, _x: int, y: int):
        if (datetime.datetime.now() - self._last_scroll_time).microseconds / 1000 > 100:
            tree_ctrl_size: wx.Size = self._grid_ctrl.GetSize()
            if y < tree_ctrl_size.GetHeight() / 6:
                self._grid_ctrl.ScrollLines(-1)
            if y > tree_ctrl_size.GetHeight() * 5 / 6:
                self._grid_ctrl.ScrollLines(1)
            self._last_scroll_time = datetime.datetime.now()



class BasicGrid(wx.grid.Grid):
    # noinspection SpellCheckingInspection
    filterImg = '32:32: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:AAAAAAFLhqvQ4v///////////////+LQq4c2AQAAAAAAAlHn////////////////////////////////51ECAAAJ/////////////////////////////////////wkAABL/////////////////////////////////////EgAAFv////////////////////////////////////8WAAAW/////////////////////////////////////xYAABb/////////////////////////////////////FgAAFv////////////////////////////////////8WAAAVwf//////////////////////////////////wRUAAA0uwf///////////////////////////////8EuDQAABBQywf/////////////////////////////BMhQEAAAAAxQywf//////////////////////////wTIUAwAAAAAAAxQywf///////////////////////8EyFAMAAAAAAAAAAxQywf/////////////////////BMhQDAAAAAAAAAAAAAxQywf//////////////////wTIUAwAAAAAAAAAAAAAAAxQywf///////////////8EyFAMAAAAAAAAAAAAAAAAAAxQywf/////////////BMhQDAAAAAAAAAAAAAAAAAAAAAxQywf//////////wTIUAwAAAAAAAAAAAAAAAAAAAAAAAxQyv////////78yFAMAAAAAAAAAAAAAAAAAAAAAAAAAAxQz////////MxQDAAAAAAAAAAAAAAAAAAAAAAAAAAAAAx3///////8dAwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFv///////xYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAW////////FgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABb///////8WAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFv///////xYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVwf//////FgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA0uwf////8WAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABBQywf///xYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAxQyxf//FgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAxQuPzIRAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABA0VEQYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    filterClearImg = '32:32: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:AAAAAUuGq9Di////////////////4tCrhzYBAAAAAAACUef////////////////////////////////nUQIAAAn/////////////////////////////////////CQAAEv////////////////////////////////////8SAAAW/////////////////////////////////////xYAABb/////////////////////////////////////FgAAFv////////////////////////////////////8WAAAW/////////////////////////////////////xYAABXB///////////////////////////////////BFQAADS7B////////////////////////////////wS4NAAAEFDLB/////////////////////////////8EyFAQAAAADFDLB///////////////////////////BMhQDAAAAAAADFDLB////////////////////////wTIUAwAAAAAAAAADFDLB/////////////////////8EyFAMAAAAAAAAAAAADFDLB///////////////////BMhQDAAAAAAAAAAAAAAADFDLB////////////////vTIUAwAAAAb/BgAAAAAAAAADFDLB//////////////9AFAMAAAEm//YQAAAAAAAAAAADFDLB//////////////8KAAABOP//PBAAAAAAAAAAAAADFDK/////////+v///+QFAl///3IeBgAAAAAAAAAAAAADFDP///////9Mzv///8qk//+iJQkAAAAAAAAAAAAAAAADHf///////y80pP//////3S0OAQAAAAAAAAAAAAAAAAAW////////GhMtmP////42FAMAAAAAAAAAAAAAAAAAABb///////8WAy3//////2sGAAAAAAAAAAAAAAAAAAAAFv///////xhc//////D//08BAAAAAAAAAAAAAAAAAAAW////////bP////+/SMH//ycBAAAAAAAAAAAAAAAAABXB////////////6jQkMob//xMAAAAAAAAAAAAAAAAADS7B//////////9RFwcRKFX/8QYAAAAAAAAAAAAAAAAEFDLB////////hB8GAAILIDj4/wYAAAAAAAAAAAAAAAADFDLC/////7InCwEAAAEHHDEmCwAAAAAAAAAAAAAAAAADFDGn///ELhACAAAAAAAFEBAGAAAAAAAAAAAAAAAAAAAEEis9Py4UAwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADCxQVDQQAAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    sortAscImg = '32:32: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:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB7F/msAAQAAg/3+//+kAAUAAAAAAAAAAAAAAAAAAQAdz//9/3cAAwCy//v//7IAAwAAAAAAAAAAAAAAAAAAE87/+v/6/38AAKz/+///sAADAQAAAAAAAAAAAAAAABbZ//v////8/4MAtf/9//+1AAMBAAAAAAAAAAAAAAAAJv/8////////rgCG9vb29n4AAAAAAAAAAAAAAAAAAAAQIor/+///8D8kCCJSWVhTNhsYEAAAAAAAAAAAAAAAAAIAcP/6///rEgYAgf/////////jFwABAAAAAAAAAAAAAABn//r//+sFAACw/vn+/f39+/8sAAEAAAAAAAAAAAAAAGj/+v//6wYAAK3/+//////9/S8AAQAAAAAAAAAAAAAAaP/6///rBgAArv75/v7+/vv/MAABAAAAAAAAAAAAAABo//r//+sGAACs/////////+glAAAAAAAAAAAAAAAAAGj/+v//6wYABDBWWFhYWFhYQhIBAQAAAAAAAAAAAAAAaP/6///rBgAAcvP19fX19fX2+/v7nQAFAAAAAAAAAABo//r//+sGAACv//3///////////+yAAQAAAAAAAAAAGj/+v//6wYAAK7/+////////////7EAAwEAAAAAAAAAaP/6///rBgAAsfv3+/v7+/v7+/v7tAADAQAAAAAAAABo//r//+sGAACa//////////////+eAgUCAAAAAAAAAGj/+v//6wYAAy1eZGNjY2NjY2NkXycAAAAAAAAAAAAAaP/6///rBgABZNze3t/f39/f39/e4ePj1hcAAAAAAABo//r//+sGAACt////////////////////KgAAAAAAAGv/+f//8QYAAK7++v7+/v7+/v7+/v7+/P4wAAAAAAAAZf/////qBgAAsv/6///////////////9/zEAAAAAAAAwmKalpW0JAACp///////////////////+LQAAAAAAAAcOFRUTCwYAA0eHi4qKioqKioqKioqKim0XAAAAAAAAAQUGBgYEAAACBw4REREREREREREREREQCgYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    sortDescImg = '32:32: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:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADk9ZWFgwAAAAg/3+/v/////////////+/yEAAAAAAABS/////9gAAACy//v///////////////3/LgAAAAAAAGn78vn57QMAAK3/+////////////////f8wAAAAAAAAaP/6///qBgAAsv/9/////////////////zEAAAAAAABo//r//+sGAACC9vb29vb29vb29vb6///gJwAAAAAAAGj/+v//6wYABCNRWFdYWFhYWFhYWE5AQzAOAAAAAAAAaP/6///rBgAAgf//////////////qQASCQMAAAAAAABo//r//+sGAACw/vn+/v7+/v7+/v6wAAIAAAAAAAAAAGj/+v//6wYAAKz/+////////////7AAAwEAAAAAAAAAaP/6///rBgAAsf35/v7+/v7+/v79tAADAQAAAAAAAABo//r//+sGAACQ//////////////+VAAIAAAAAAAAAAGj/+v//6wYABCZSWVhYWFhYWFhZVCoEAAAAAAAAAAAAaP/6///rBgAAc/P19fX19fX0KggNBgEAAAAAAAAAAABo//r//+sGAACv//3///////8rAAAAAAAAAAAAAAAAAGj/+v//6wYAAK7/+//////9/zAAAQAAAAAAAAAAAAAAaP/6///rBgAAsfv3+/v7+/n/MAABAAAAAAAAAAAAAAJp//r//+sIAQCa//////////cqAAEAAAAAAAAAAAAAAGD/+v//6gAAAy1eZGNjaHFwVxQAAAAAAAAAAAAAABnq7v/+///95ZIBaNze39+OABIJBAAAAAAAAAAAAAAAI////v//////pQCx/////7QABAAAAAAAAAAAAAAAAAADSfL//f///7cQAK3++v7+sQADAQAAAAAAAAAAAAAAAAQHUfD//v+2GQwAsv/6//+yAAMBAAAAAAAAAAAAAAAAAAQFVez/rRkOAACp/////7oAAwEAAAAAAAAAAAAAAAAAAAYJXYQhCwAAA0eHi4uJVgQBAAAAAAAAAAAAAAAAAAAAAAcMCw0BAAACBw4RERAHAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
    # noinspection SpellCheckingInspection
    sortAscCheckedImg = '32:32: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:7fLy8vPy9vb29vb29vb29vb28vLy8vLy8vPz8/Ly8vr2PG5ubm5ubm5ubm5ubm5ubmVlZWVlZWVubm5ubmVl9/ZlAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAG739mUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAbvf2ZQAAAB7F/msAAQAAg/3+//+kAAUAAAAAAAAAAABu9/ZlAQAdz//9/3cAAwCy//v//7IAAwAAAAAAAAAAAG739WUAE87/+v/6/38AAKz/+///sAADAQAAAAAAAAAAbvr1ZRbZ//v////8/4MAtf/9//+1AAMBAAAAAAAAAABu+vVlJv/8////////rgCG9vb29n4AAAAAAAAAAAAAAG769WUQIor/+///8D8kCCJSWVhTNhsYEAAAAAAAAAAAbvr1ZQIAcP/6///rEgYAgf/////////jFwABAAAAAABu+vVlAABn//r//+sFAACw/vn+/f39+/8sAAEAAAAAAG769WUAAGj/+v//6wYAAK3/+//////9/S8AAQAAAAAAbvr1ZQAAaP/6///rBgAArv75/v7+/vv/MAABAAAAAABu+vZlAABo//r//+sGAACs/////////+glAAAAAAAAAG769mUAAGj/+v//6wYABDBWWFhYWFhYQhIBAQAAAAAAbvr2ZQAAaP/6///rBgAAcvP19fX19fX2+/v7nQAFAABu+vZlAABo//r//+sGAACv//3///////////+yAAQAAGX69mUAAGj/+v//6wYAAK7/+////////////7EAAwEAZff2ZQAAaP/6///rBgAAsfv3+/v7+/v7+/v7tAADAQBl9/ZtAABo//r//+sGAACa//////////////+eAgUCAGX39WUAAGj/+v//6wYAAy1eZGNjY2NjY2NkXycAAAAAZff1ZQAAaP/6///rBgABZNze3t/f39/f39/e4ePj1hdl9/VlAABo//r//+sGAACt////////////////////KmX39WUAAGv/+f//8QYAAK7++v7+/v7+/v7+/v7+/P4wbvf1ZQAAZf/////qBgAAsv/6///////////////9/zFu9/VlAAAwmKalpW0JAACp///////////////////+LW739WUAAAcOFRUTCwYAA0eHi4qKioqKioqKioqKim0XbvfybQAAAQUGBgYEAAACBw4REREREREREREREREQCgZu9/VlAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGX38mVlZWVlZWVlZWVlZWVlZWVlZWVtZWVlZWVlZW1lhff9+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn5+fn59/n3/g=='
    # noinspection SpellCheckingInspection
    sortDescCheckedImg = '32:32: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:/v39/f7+/v7+/v7+/v7+/v7+/v7+/v7+/f7+/v39/f7hPG5ubm5ubm5ubm5ubm5ubmVlZWVlZWVubm5ubmVl9+FlAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAG734WUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAbvfhZQAADk9ZWFgwAAAAg/3+/v/////////////+/yFu9+FlAABS/////9gAAACy//v///////////////3/Lm734WUAAGn78vn57QMAAK3/+////////////////f8wbvrhZQAAaP/6///qBgAAsv/9/////////////////zFu+uFlAABo//r//+sGAACC9vb29vb29vb29vb6///gJ2764WUAAGj/+v//6wYABCNRWFdYWFhYWFhYWE5AQzAObvrhZQAAaP/6///rBgAAgf//////////////qQASCQNu+uFlAABo//r//+sGAACw/vn+/v7+/v7+/v6wAAIAAG764WUAAGj/+v//6wYAAKz/+////////////7AAAwEAbvrhZQAAaP/6///rBgAAsf35/v7+/v7+/v79tAADAQBu+uFlAABo//r//+sGAACQ//////////////+VAAIAAG764WUAAGj/+v//6wYABCZSWVhYWFhYWFhZVCoEAAAAbvrhZQAAaP/6///rBgAAc/P19fX19fX0KggNBgEAAABu+uFlAABo//r//+sGAACv//3///////8rAAAAAAAAAGX64WUAAGj/+v//6wYAAK7/+//////9/zAAAQAAAAAAZffhZQAAaP/6///rBgAAsfv3+/v7+/n/MAABAAAAAABl9+FtAAJp//r//+sIAQCa//////////cqAAEAAAAAAGX34WUAAGD/+v//6gAAAy1eZGNjaHFwVxQAAAAAAAAAZffhZRnq7v/+///95ZIBaNze39+OABIJBAAAAAAAAABl9+FlI////v//////pQCx/////7QABAAAAAAAAAAAAGX34WUDSfL//f///7cQAK3++v7+sQADAQAAAAAAAAAAbvfhZQQHUfD//v+2GQwAsv/6//+yAAMBAAAAAAAAAABu9+FlAAQFVez/rRkOAACp/////7oAAwEAAAAAAAAAAG734WUAAAYJXYQhCwAAA0eHi4uJVgQBAAAAAAAAAAAAbvfdbQAAAAcMCw0BAAACBw4RERAHAgAAAAAAAAAAAABu9+FlAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGX33WVlZWVlZWVlZWVlZWVlZWVlZWVtZWVlZWVlZW1lhff+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/w=='
    # noinspection SpellCheckingInspection
    sortConfigImg = '32:32:////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////AAAATYVJSoRHR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFSoRHT4dLAAAA////////AAAAQoK2QYK4P4G3P4G3QYK4QoK2AAAA////////AAAASoRH2ui31uS21uS41uS41uS41uS41uS41uS41uS41uS41uS41uS41uS41uS41uS22ui3SoRHAAAA////////AAAAQIK4u9rvo8zoo8zou9rvQIK4AAAA////////AAAASYNHzOGpdKopdastdqstdqstdqstdqstdqstdqstdqstdqstdqstdqstdastdKopzOGpSYNHAAAA////////AAAAPoG3udruQZPLQZPLudruPoG3AAAA////////AAAASYNIuNmJib5Li75Oi75Pi75Pi75Pi75Pi75Pi75Pi75Pi75Pi75Pi75Pi75Oib5LuNmJSYNIAAAA////////AAAAPoG3u9ruRpXMRpXMu9ruPoG3AAAA////////AAAATIVKr9x4otVqotRrotVrotVrotVrotVrotVrotVrotVrotVrotVrotVrotRrotVqr9x4TIVKAAAA////////AAAAPoC3u9vvSJjPSJjPu9vvPoC3AAAA////////AAAASHpETIVLS4RKS4NLS4NLS4NLS4NLS4NLS4NLS4NLS4NLS4NLS4NLS4NLS4NLS4RKTIVLSHpEAAAA////////AAAAPoC2vNzwSpnQSpnQvNzwPoC2AAAA////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////AAAAPoC2vNzwTZvSTZvSvNzwPoC2AAAA////////AAAATIJISoRHR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFR4JFSoRHToZKAAAAAAAAAAAAAAAAAAAA////////AAAAPoC2udrwTp3TTp3TudrwPoC2AAAA////////AAAASoRH2ui31uS21uS41uS41uS41uS41uS41uS41uS41uS41uS22ui3SoRHAAAA////////////////////////AAAAP4C2tNnwUJ/UUJ/UtNnwP4C2AAAA////////AAAASYNHzOGpdKopdastdqstdqstdqstdqstdqstdqstdastdKopzOGpSYNHAAAA////////////////////////AAAAP4G2sdbvU6LXU6LXsdbvP4G2AAAA////////AAAASYNIuNmJib5Li75Oi75Pi75Pi75Pi75Pi75Pi75Pi75Oib5LuNmJSYNIAAAA////////////////////////AAAAP4G2rdXvVqPYVqPYrdXvP4G2AAAA////////AAAATIVKr9x4otVqotRrotVrotVrotVrotVrotVrotVrotRrotVqr9x4TIVKAAAA////////////////////////AAAAP4G2qtTuV6XaV6XaqtTuP4G2AAAA////////AAAASHpETIVLS4RKS4NLS4NLS4NLS4NLS4NLS4NLS4NLS4NLS4RKTIVLSHpEAAAA////////////////////////AAAAP4G2ptLuWabbWabbptLuP4G2AAAA////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////////////////AAAAQIG2o9HvXKncXKnco9HvQIG2AAAA////////AAAATIJISoRHR4JFR4JFR4JFR4JFR4JFR4JFSYJGeox8jY+SjY+SiImLAAAAAAAAAQAAAQAAAQAAAQAA////////AAAAQIG2n8/vXqvfXqvfn8/vQIG2AAAA////////AAAASoRH2ui31uS21uS41uS40+G2oaackZSTy9irh4mM8/P08/P0h4mMAAAAi42QioyPAAAAAQAAAQAA////////AAAAQIG2nM7vYKzgYKzgnM7vQIG2AAAA////////AAAASYNHzOGpdKopdastdaktf5JusbO0u72/goSGo6On1NbY1NbYo6OngoSGu72/sbO0hIaIAAAAAQAA////////AAAAQIG2mMzvY67iY67imMzvQIG2AAAA////////AAAASYNIuNmJib5Li75OhLVLhouGtri65ubn5OTl7Ozut7m7t7m77Ozu5OTl5ubntri6hYeKAAAAAQAA////////AAAAQYG2lsvwZa/jZa/jlsvwQYG2AAAA////////AAAATIVKr9x4otVqotRrmspmg6xXfX+CtLa5yszOpaapiYuNjI6RpaapyszOtLa5fX+CAAAAAAAAAQAA////////AAAAQYG2lMvwaLLlaLLllMvwQYG2AAAA////////AAAASHpDTIVLS4RKSoFKbYBwfH6BnJ2gz9DSpqirfX+DOjs9QEFDfX+Dpqirz9DSnJ2gfH6BfX+CAAAA////////AAAAQYG2ksrxabTnabTnkcrxQYG2AAAA////////AAAAAAAAAAAAAAAAAAAAfH6A6+zu5ufowMLEi42QNzg4AAAAAAAAREVGhoiLwcPE5ufp6+zufH6AAAAAAAAARYS5QoK3Pn6zebXgX6faX6faeLXgPn6zQoK3RYS7AAAAAAAATIJGSoRHR4JFQnhAeXt91dXXy8zNxcbJioyOSElLAAAAAAAAT1BSioyOxcbJy8zN1dXXeXt9AAAAAAAARIS4j873isnyfsHub7nqb7nqg8Puisnyj873RIS7AAAAAAAASoRF2ui31uS2xdKoiI2DdHZ6jI6RzM7QsLK0c3V4ZWdpZWdpc3V4sLK0zM7QjI6RdHZ6bW9xAAAAAAAAAAAAQYG1dsHycrztcbrscbrscrztdsHyQYG2AAAAAAAAAAAASYNFzOGpc6oobqImqbuMQmRCbnBzy8zO0NHTsrS2iIqMgYKFs7W30NHTy8zObnBzODk7AAAAAAAAAAAAAAAAAAAAQYC1ecLydb7vdb7vecLyQYC1AAAAAAAAAAAAAAAASYNIuNmJib1Kh7tJqsh/bnVxp6mr2trez9HT1tfa1dbZ1dbZ1tfaz9HT2trep6mrcXN1AAAAAAAA////AAAAAAAAAAAAQYC1fcb2fcb2QYC1AAAAAAAAAAAA////AAAATIVKr9x4otVpotVppdBxYHFjnJyep6mrZ2lrkpOV29ze29zeiouNZ2lrp6mrnJyeaGpsAAAAAQAA////////AAAAAAAAAAAARIO3RIO3AAAAAAAAAAAA////////AAAASn5HTIVLS4RKS4RKSX9IQG09X2FjaWttAAAAZ2lr6ers6ersZ2lrAAAAaWttYmRmAAAAAAAAAQAA////////////AAAAAAAAAAAAAAAAAAAAAAAA////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAX2FiZ2lrZ2lrX2FiAAAAAAAAAAAAAAAAAAAAAQAA////////////////AAAAAAAAAAAAAAAA////////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAA////////////////////////////////////////////////////////////////AQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAA:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAS0//////////////////////AFAAAEtP////+0BAAADf///////////////////////xAAAA3///////8NAAAV////////////////////////FgAAFf///////xUAABb///////////////////////8WAAAW////////FgAAFv///////////////////////xYAABb///////8WAAAVwv/////////////////////EFQAAFv///////xYAAA0rP0NDQ0NDQ0NDQ0NDQ0NDPysNAAAW////////FgAACLb////////////////tGxYVDQQAABb///////8WAAAN//////////////////8QAAAAAAAAFv///////xYAABX//////////////////xYAAAAAAAAW////////FgAAFv//////////////////FgAAAAAAABb///////8WAAAW//////////////////8WAAAAAAAAFv///////xYAABXC////////////////xBUAAAAAAAAW////////FgAADSs/Q0NDQ0NDQ0NDQz8rDQAAAAAAABb///////8WAAAItv//////////+v//uREEAAAAAAAAFv///////xYAAA3/////////////////Euu0BAAAAAAW////////FgAAFf////////////////////+2BAAAABb///////8WAAAW/////////////////////+4NAAAAFv///////xYAABb/////////////////////Mg4AAAAW////////FgAAFcL///////////+Bdf//////tAQAABb///////8WAAANKz9DTf//////hjUqbf//////DQXw///////////wBQi2//////////9jEQ1a//////8VEP////////////8QDf////////////9ERP//////wRUQN///////////NxAV/////////////////////20sDQYcPf///////z0cBhb/////////////////////7RQEAAYcPf////89HAYAFv////////////////////+/DwAAAAYcPf//PRwGAAAV1P/////2zPFN/////03xxy4NAAAAAAYcNzccBgAAAA4tQENDRUI8Mi/E///ELzIuFQQAAAAAAAYREQYAAAAABA4VFhYWFBIOEis/PysSDg0EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEDRUVDQQAAAAAAA=='
    # noinspection SpellCheckingInspection
    filterConfigImg = '32:32:////////////////AAAAP32vPn6yPn6zPoC1PX+2PoG3PYC3PYC3PYC3PYC3PYC3PYC3PYC3PYC3PYG3PoG3PoG3Pn+2P4C1P3+0QH+yPnqrAAAA////////////////////AAAAP3usP4G3UY2+bJ/JibHTpMLdrMjgvtLl0N3sztzrzNzqy9zqy9roydnoyNnoyNroyNroydnpyNrpytnquc7jp8Tdnb7bha/Sap3HUI2+QIK4QHusAAAA////////AAAAQIK4rcngudLkibfVdq3QS5bFUZrJOY7ENY7GPJPLQpnPSJ3UT6PZVqndWargUaXbTKDWRZrRP5bMOJDIOpDFU5zJTJbFc6vPhbTUsM3hpsTeQYO5AAAA////////AAAAPoC2y+7/AGOhDG6qF3axIn64K4W9NIvCO5DGQpbMR5vQTZ/UVKTYWqrdXavfVqfbUaHWS5zRRJjNPpPJNo3ELoi/JoG6HHq0EXKvBGmmosjjQIK4AAAA////////AAAAPH+1x+r/sdr0l8XggbfZUJnHVp/LNozCMorCOZDIPpXNRZrSTKDWVKbbVqfdT6PZSp3VQ5jPPZTLN4/HOpDFVJ3LTpjGda7Th7fXjLvaocfjQIK4AAAA////////AAAAPH61xuj/eMT1i833qdv6t+L90e3+0+7/6/n/5/f/5fT+4vL94PH63e752e342uz21+r31en11On11Of0stPrr9Lpjb7febLYUpnMOonCosjjQIK4AAAA////////AAAAPH+1xej/dsLzfMTzgMbzgsn0hcr0iMv1is71hsrygcbvfMHseL7pc7rmbrbjarPfZa7cYKraW6bXWKPUVaDRUJzOTZnMSZbJRJHHPIvCo8njQYK4AAAA////////AAAAPoC2vuL4t9/7jMv1e8Tyf8fzhMr0iMv1i871iMvyhMfvgMPtfMDqd7znc7jkb7XharHeZq3cYanZXqbWWqPTVZ/QUZzNSpbJQpDGOorCqMrhQoO5AAAA////////AAAAO3SjYavf7Pn/////2+/8xeX6rtv3qNr3m9T2ldD0kczxfsLte7/qd7znc7jkcLbhbLLeaK7cY6rZYKjWWaLSU53OS5fKPo3Ers7lsNHlOIS7PXamAAAA////////AAAAAAAAN2+dXqnew+b93PD9oNP2veL4veL5zur7xeX5uuD2sdnyptPvmszsjcTogLzicrPdY6nXXKTVV6DQUZzNSpXJP47FoMfho8jiNoO7O3KgAAAAAAAA////////AAAAAAAAAAAAN2+dYKreuuL8sdz5cr/xfcXyh8v0isv0hMfvf8Pse7/pdrrncrfibbPgabDdZazaYKfWW6PTU53PSZfLmcTgncXiOoW9O3KgAAAAAAAAAAAA////////////AAAAAAAAAAAAN2+dYqves9/7rdr4esPzhcn0jc71isvyhMfvf8Pser/odrrlcbbibLLfZ67bYqrYW6TVUp7Qk8LhlsPhQYvBO3KgAAAAAAAAAAAA////////////////////AAAAAAAAAAAAN2+dZKverdv7ptj4f8bzi8z0js70iMnxg8XtfsHqeb3ndLjkb7TgarDdY6vaW6XWj8HhkMHiR5DEO3KgAAAAAAAAAAAA////////////////////////////AAAAAAAAAAAAOG+eZKzfpNf6otX4hcn0jc/1i8zyhsfvgcPsfL/pd7vlcrbibLHfZazbisDjjMHiTZbIO3KfAAAAAAAAAAAA////////////////////////////////////AAAAAAAAAAAAOHCeZazfndX6ndT3icz0js30iMrxg8XufsHqeb3nc7nkbbThh8DlicDkVJvNOnKfAAAAAAAAAAAA////////////////////////////////////////////AAAAAAAAAAAAOHCeZazel9P4mNP3jc/2i8zzhsjvgcPsfL/pdrrmhMDohsLmWqDQOnKfAAAAAAAAAAAA////////////////////////////////////////////////////AAAAAAAAAAAAOHCdaK7gk9H6lNH3jc/1icrxhMbuf8Hrg8PqhcTpYaTUN26bgYOFjY+SjY+SjY+RAAAAAQAAAQAAAQAAAQAAAQAA////////////////////////////////AAAAAAAAAAAAOHCda7DgjtD5jtD3jMz0h8jwgsXugsPrf5WlhYuQAAAAh4mM8/P08/P0h4mMAAAAi42QioyPAAAAAQAAAQAA////////////////////////////////////AAAAAAAAAAAAOG+cUJTI0O3+isz1eL7otdTpdYubsbO0u72/goSGo6On1NbY1NbYo6OngoSGu72/sbO0hIaIAAAAAQAA////////////////////////////////////////AAAAAAAAAAAAOXyz8/3/gsfxYarb1+LpgIaNtri65ubn5OTl7Ozut7m7t7m77Ozu5OTl5ubntri6hYeKAAAAAQAA////////////////////////////////////////////AAAAAAAAOn205fj/g8jyYavbxNjkMWeTfX+CtLa5yszOpaapiYuNjI6RpaapyszOtLa5fX+CAAAAAAAAAQAA////////////////////////////////////////////////AAAAOn612/L/hMjyYqrZkJqhfH6BnJ2gz9DSpqirfX+DQEFDQEFDfX+Dpqirz9DSnJ2gfH6BfX+CAAAA////////////////////////////////////////////////AAAAPH61zu7/hcnyX6XRfH6A6+zu5ufowMLEi42QREVGAAAAAAAAREVGhoiLwcPE5ufp6+zufH6AAAAA////////////////////////////////////////////////AAAAPH61wun/h8ryXqDKeXt91dXXy8zNxcbJioyOT1BSAAAAAAAAT1BSioyOxcbJy8zN1dXXeXt9AAAA////////////////////////////////////////////////AAAAPn+2ueT/icvzX6HLdYKMdHZ6jI6RzM7QsLK0c3V4ZWdpZWdpc3V4sLK0zM7QjI6RdHZ6bW9xAAAA////////////////////////////////////////////////AAAAO3Sjg73ljc/2ZajTZZW0PmSDbnBzy8zO0NHTsrS2iIqMgYKFs7W30NHTy8zObnBzODk7AAAAAAAA////////////////////////////////////////////////AAAAAAAAOHCecbLebrPeYZzFbXV6p6mr2trez9HT1tfa1dbZ1dbZ1tfaz9HT2trep6mrcXN1AAAAAAAA////////////////////////////////////////////////AAAAAAAAAAAAOnGfXqLRVZjFX3GAnJyep6mrZ2lrkpOV29ze29zeiouNZ2lrp6mrnJyeaGpsAAAAAQAA////////////////////////////////////////////////////AAAAAAAAAAAAPHSiQn+wOm6aX2FjaWttAAAAZ2lr6ers6ersZ2lrAAAAaWttYmRmAAAAAAAAAQAA////////////////////////////////////////////////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAX2FiZ2lrZ2lrX2FiAAAAAAAAAAAAAAAAAAAAAQAA////////////////////////////////////////////////////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAA////////////////////////////////////////////////////////////////AQAAAQAAAQAAAQAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAQAAAQAA:AAAAAAFLhqvQ4v///////////////+LQq4c2AQAAAAAAAlHn////////////////////////////////51ECAAAJ/////////////////////////////////////wkAABL/////////////////////////////////////EgAAFv////////////////////////////////////8WAAAW/////////////////////////////////////xYAABb/////////////////////////////////////FgAAFv////////////////////////////////////8WAAAVwf//////////////////////////////////wRUAAA0uwf///////////////////////////////8EuDQAABBQywf/////////////////////////////BMhQEAAAAAxQywf//////////////////////////wTIUAwAAAAAAAxQywf///////////////////////8EyFAMAAAAAAAAAAxQywf/////////////////////BMhQDAAAAAAAAAAAAAxQywf//////////////////wTIUAwAAAAAAAAAAAAAAAxQywf///////////////8EyFAMAAAAAAAAAAAAAAAAAAxQywf/////////////Cwv//sgQAAAAAAAAAAAAAAAAAAxQywf//////////+0H/////Euu0BAAAAAAAAAAAAAAAAxQyv/////////////////////+2BAAAAAAAAAAAAAAAAxQz/////////////////////+4NAAAAAAAAAAAAAAAAAx3/////////////////////Mg4AAAAAAAAAAAAAAAAAFv////////////91df//////tAQAAAAAAAAAAAAAAAAW////////////bSoqbf//////DQAAAAAAAAAAAAAAABb///////////9aDQ1a//////8VAAAAAAAAAAAAAAAAFv////////////9ERP//////wRUAAAAAAAAAAAAAAAAVwf///////////////////20sDQAAAAAAAAAAAAAAAA0uwf//////////////////7RQEAAAAAAAAAAAAAAAABBQywf////////////////+/DwAAAAAAAAAAAAAAAAAAAxQyxf//zPFN/////03xxy4NAAAAAAAAAAAAAAAAAAAAAxQuQ0M8Mi/E///ELzIuFQQAAAAAAAAAAAAAAAAAAAAABA0VFRMOEis/PysSDg0EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEDRUVDQQAAAAAAA=='

    table: 'BasicTable'
    _double_buffered: bool
    _can_drag_rows: bool
    _can_drag_cols: bool
    _col_popup_wnd: Optional[wx.PopupTransientWindow]
    _cur_row_count: int
    _cur_col_count: int

    can_drag_and_drop: bool
    can_drop_to_cell: Optional[Callable[[wx.grid.GridCellCoords], bool]]
    can_drop_to_cell_data: Optional[Callable[[wx.grid.GridCellCoords, Any], bool]]
    drop_to_cell_execute: Optional[Callable[[wx.grid.GridCellCoords, Any, int], int]]
    can_select_all: bool = False
    bitmaps: Dict[str, wx.Bitmap]
    on_paint_col_header_cell: Optional[Callable[[int, wx.Rect, wx.DC], None]] = None
    on_paint_row_header_cell: Optional[Callable[[int, wx.Rect, wx.DC], None]] = None
    on_control_c_callback: Optional[Callable[['BasicGrid'], None]] = None
    def __init__(self, parent: Union[wx.Frame, wx.Dialog, wx.Panel], table: BasicTable, double_buffered: bool = True, can_drop: bool = True):
        # внимание IncRef, DecRef применятся если GridAttr, Editor, Renderer один и тот же используется несколько раз!!!
        #attr.IncRef, editor.IncRef, renderer.DefRef
        # attr.DecRef, editor.DecRef, renderer.DefRef
        self.can_drag_and_drop = can_drop
        self._parent = parent
        wx.grid.Grid.__init__(self, parent, wx.ID_ANY)
        self.table = table
        self._double_buffered = double_buffered
        self._can_drag_cols = True
        self._can_drag_rows = True
        self._cur_col_count = 0
        self._cur_row_count = 0

        self.can_drop_to_cell = None
        self.can_drop_to_cell_data = None
        self.drop_to_cell_execute = None
        self.can_select_all = True


        self.SetDoubleBuffered(double_buffered)

        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)  # обработка Ctrl+C, Ctrl+V так как grid обрабатывает их неверно
        wnd1: wx.Window = self.GetGridColLabelWindow()
        wnd1.Bind(wx.EVT_PAINT, self._on_paint_col_header)
        wnd1.Bind(wx.EVT_MOUSE_EVENTS, self._on_mouse_move)
        wnd2: wx.Window = self.GetGridRowLabelWindow()
        wnd2.Bind(wx.EVT_PAINT, self._on_paint_row_header)
        wnd2.Bind(wx.EVT_MOUSE_EVENTS, self._on_mouse_move)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        self.Bind(wx.grid.EVT_GRID_COL_SIZE, self._on_col_resize)
        self.Bind(wx.grid.EVT_GRID_ROW_SIZE, self._on_row_resize)
        #self.Bind(wx.grid.EVT_GRID_COL_AUTO_SIZE, self._on_col_auto_resize)

        self.Bind(wx.grid.EVT_GRID_LABEL_LEFT_CLICK, self._on_label_click)
        self.Bind(wx.grid.EVT_GRID_LABEL_RIGHT_CLICK, self._on_label_rclick)

        self.Bind(wx.grid.EVT_GRID_COL_MOVE, self._on_col_move)
        self.Bind(wx.grid.EVT_GRID_ROW_MOVE, self._on_row_move)

        self.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self._on_cel_left_click)
        self.Bind(wx.grid.EVT_GRID_CELL_LEFT_DCLICK, self._on_cel_left_dclick)
        self.Bind(wx.grid.EVT_GRID_CELL_RIGHT_CLICK, self._on_cel_right_click)
        self.Bind(wx.grid.EVT_GRID_RANGE_SELECTED, self._on_selection_changed)


        table.set_grid(self)
        self.SetTable(table,True)

        self._col_popup_wnd = None

        self.bitmaps = {'sort_asc': _base64_str_to_image(self.sortAscImg).Scale(GuiWidgetSettings.grid_header_icon_size, GuiWidgetSettings.grid_header_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap(),
                        'sort_desc': _base64_str_to_image(self.sortDescImg).Scale(GuiWidgetSettings.grid_header_icon_size, GuiWidgetSettings.grid_header_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap(),
                        'sort_asc_checked': _base64_str_to_image(self.sortAscCheckedImg).Scale(GuiWidgetSettings.grid_header_icon_size, GuiWidgetSettings.grid_header_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap(),
                        'sort_desc_checked': _base64_str_to_image(self.sortDescCheckedImg).Scale(GuiWidgetSettings.grid_header_icon_size, GuiWidgetSettings.grid_header_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap(),
                        'sort_config': _base64_str_to_image(self.sortConfigImg).Scale(GuiWidgetSettings.grid_header_icon_size, GuiWidgetSettings.grid_header_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap(),
                        'filter': _base64_str_to_image(self.filterImg).Scale(GuiWidgetSettings.grid_header_icon_size, GuiWidgetSettings.grid_header_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap(),
                        'filter_clear': _base64_str_to_image(self.filterClearImg).Scale(GuiWidgetSettings.grid_header_icon_size, GuiWidgetSettings.grid_header_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap(),
                        'filter_config': _base64_str_to_image(self.filterConfigImg).Scale(GuiWidgetSettings.grid_header_icon_size, GuiWidgetSettings.grid_header_icon_size, wx.IMAGE_QUALITY_BICUBIC).ConvertToBitmap()}
        if self.can_drag_and_drop:
            self._drop_file_target = BasicGridDropTarget(self)
            self.SetDropTarget(self._drop_file_target)


    @property
    def can_drag_rows(self):
        return self._can_drag_rows

    @can_drag_rows.setter
    def can_drag_rows(self, value):
        self._can_drag_rows = value

    @property
    def can_drag_cols(self):
        return self._can_drag_cols

    @can_drag_cols.setter
    def can_drag_cols(self, value):
        self._can_drag_cols = value

    #region Основные функции

    def update_view(self):
        self.BeginBatch()
        col_difference = self.GetNumberCols() - self._cur_col_count
        msg = None
        if col_difference!=0:
            if col_difference>0:
                msg = wx.grid.GridTableMessage(self.table, wx.grid.GRIDTABLE_NOTIFY_COLS_APPENDED, col_difference)
            else:
                msg = wx.grid.GridTableMessage(self.table, wx.grid.GRIDTABLE_NOTIFY_COLS_DELETED, self._cur_col_count, abs(col_difference))
        if msg:
            self._cur_col_count = self.GetNumberCols()
            self.ProcessTableMessage(msg)


        row_difference = self.GetNumberRows() - self._cur_row_count
        msg = None
        if row_difference != 0:
            if row_difference > 0:
                msg = wx.grid.GridTableMessage(self.table, wx.grid.GRIDTABLE_NOTIFY_ROWS_APPENDED, row_difference)
            else:
                msg = wx.grid.GridTableMessage(self.table, wx.grid.GRIDTABLE_NOTIFY_ROWS_DELETED, self._cur_row_count-abs(row_difference), abs(row_difference))
        if msg:
            self._cur_row_count = self.GetNumberRows()
            self.ProcessTableMessage(msg)
        self.EndBatch()

    def update_col_header(self):
        """обновление заголовка после отрисовки"""
        w: wx.Window = self.GetGridColLabelWindow()
        w.Refresh()

    def update_row_header(self):
        """обновление заголовка после отрисовки"""
        w1: wx.Window = self.GetGridRowLabelWindow()
        w1.Refresh()

    def show_config_dialog(self, parent):
        grid = self

        # noinspection PyProtectedMember

        if self.table.GetNumberRows()>0:
            row_default = self.table.get_row_info(0).height
            for row in range(self.table.GetNumberRows()):
                if self.table.get_row_info(row).height != row_default:
                    row_default = None
            if row_default == 0:
                row_default = grid.GetDefaultRowSize()
        else:
            row_default = grid.GetDefaultRowSize()

        if self.table.GetNumberCols()>0:
            col_default = self.table.get_column_info(0).width

            for col in range(self.table.GetNumberCols()):
                if self.table.get_column_info(col).width != col_default:
                    col_default = None
            if col_default == 0:
                col_default = grid.GetDefaultColSize()
        else:
            col_default = grid.GetDefaultColSize()

        prop_window = PropertiesWindow(parent, "Настройки отображения", None, None, wx.DefaultSize)
        #prop_window.prop_grid.add_property('font', 'Шрифт', wx.Font, self.table.default_cell_font)
        prop_window.prop_grid.add_property('col_header_height', 'Высота заголовка столбцов:', int, grid.GetColLabelSize())
        prop_window.prop_grid.add_property('row_header_width', 'Ширина заголовка строк:', int, grid.GetRowLabelSize())

        prop_window.prop_grid.add_property('cell_width', 'Ширина ячейки:', int, col_default)
        prop_window.prop_grid.add_property('cell_height', 'Высота ячейки:', int, row_default)
        # noinspection PyProtectedMember
        prop_window.prop_grid.add_property('can_resize_rows', 'Изменять размеры строк', bool, grid.table.can_resize_rows)
        # noinspection PyProtectedMember
        prop_window.prop_grid.add_property('can_resize_cols', 'Изменять размеры столбцов', bool, grid.table.can_resize_cols)
        prop_window.prop_grid.add_property('can_move_cols', 'Перемещать столбцы', bool, grid.table.can_drag_cols)
        prop_window.prop_grid.add_property('can_move_rows', 'Перемещать строки', bool, grid.table.can_drag_rows)
        prop_window.prop_grid.add_property('row_default_height', 'Высота строки по умолчанию', int, grid.GetDefaultRowSize())

        n_size: wx.Size = prop_window.GetBestSize()
        n_size.SetWidth(n_size.GetWidth()+50)
        n_size.SetHeight(n_size.GetHeight() - 30)
        prop_window.SetSize(n_size)
        prop_window.CenterOnParent()
        r = prop_window.ShowModal()
        if r == wx.ID_OK:
            frozen = grid.IsFrozen()
            if not frozen:
                grid.Freeze()
            cell_width = prop_window.prop_grid.get_property_value('cell_width')
            cell_height = prop_window.prop_grid.get_property_value('cell_height')
            if cell_width:
                for col in range(grid.GetNumberCols()):
                    grid.table.get_column_info(col).width = cell_width
            grid.update_col_sizes()
            if cell_height:
                for row in range(grid.table.GetNumberRows()):
                    grid.table.get_row_info(row).height = cell_height
            grid.update_row_sizes()
            grid.table.can_resize_cols = prop_window.prop_grid.get_property_value('can_resize_cols')
            grid.table.can_resize_rows = prop_window.prop_grid.get_property_value('can_resize_rows')
            grid.table.can_drag_cols = prop_window.prop_grid.get_property_value('can_move_cols')
            grid.table.can_drag_rows = prop_window.prop_grid.get_property_value('can_move_rows')

            grid.SetColLabelSize(prop_window.prop_grid.get_property_value('col_header_height'))
            grid.SetRowLabelSize(prop_window.prop_grid.get_property_value('row_header_width'))
            grid.SetDefaultRowSize(prop_window.prop_grid.get_property_value('row_default_height'))

            if not frozen:
                grid.Thaw()
            grid.Layout()
            grid.Update()


    def goto_cell(self, grid_cell: wx.grid.GridCellCoords):
        if grid_cell is None:
            return

        if self.GetNumberRows()>grid_cell.GetRow()>=0 and self.GetNumberCols()>grid_cell.GetCol()>=0:
            self.MakeCellVisible(grid_cell)
            self.GoToCell(grid_cell)

    def select_cells(self, grid_cells: List[wx.grid.GridCellCoords]):
        sorted_cells = sorted(grid_cells, key=lambda c: (c.GetRow(), c.GetCol()))
        cb = None
        blocks = []
        for row, col in sorted_cells:
            if cb is None:
                cb = [row, col, row, col]
            elif (row == cb[0] and col == cb[3]+1) or (row==cb[2]+1 and col==cb[1] and cb[3]-cb[1]==cb[2]-cb[0]):
                cb[2] = max(cb[2], row)
                cb[3] = max(cb[3], col)
            else:
                blocks.append(tuple(cb))
                cb = [row, col, row, col]
        if cb:
            blocks.append(tuple(cb))
        self.ClearSelection()
        for block in blocks:
            self.SelectBlock(block[0], block[1], block[2], block[3], addToSelected=True)


    def set_active_cell(self, grid_cell: wx.grid.GridCellCoords):
        if grid_cell is None:
            return

        if self.GetNumberRows()>grid_cell.GetRow()>=0 and self.GetNumberCols()>grid_cell.GetCol()>=0:
            self.goto_cell(grid_cell)
            self.SetGridCursor(grid_cell)
            self.SetFocus()

    #endregion

    # region События

    def _on_mouse_move(self, evt: wx.MouseEvent):
        # grid использует двойную буферизацию для избегания ситуаций с flicker эффектом
        # однако же, при изменении положения заголовков таблицы горизонтальная синяя черта не отображается,
        # если двойную буферизацию не выключить
        # что мы здесь и делаем, но делаем это до начала EVT_GRID_ROW_MOVE, COL_MOVE
        # потому что до начала возникновения этого события внутренние функции wxWidgets уже должны знать, что
        # двойная буферизация отключена, иначе это не возымеет эффекта, вот такой грязный хак
        # поэтому при изменении модификатора Alt в col_move, необходимо и здесь поправить, иначе перестанет работать и здесь
        # по моему так пока логично
        if evt.AltDown():
            if self.can_drag_cols and not self.CanDragColMove():
                self.EnableDragColMove(True)

            if self.can_drag_rows and not self.CanDragRowMove():
                self.EnableDragRowMove(True)


            if self._double_buffered:
                self.SetDoubleBuffered(False)

            if self._col_popup_wnd:
                self._col_popup_wnd.Dismiss()
                self._col_popup_wnd = None
        else:
            if self.CanDragColMove():
                self.DisableDragColMove()
            if self.CanDragRowMove():
                self.DisableDragRowMove()
            if self._double_buffered:
                self.SetDoubleBuffered(True)

        # не использовать Veto, иначе это все ломает
        evt.Skip()

    def _on_key_down(self, evt: wx.KeyEvent):
        # отключим все события для Ctrl+C и Ctrl+V дабы избежать проблем, когда этот код обрабатывается wxWidgets С++ кодом
        # не хочет он копировать блоки, да и вставит свою фигню
        if evt.ControlDown() and evt.GetRawKeyCode() == ord('C'):
            if self.on_control_c_callback:
                self.on_control_c_callback(self)
        elif evt.ControlDown() and evt.GetRawKeyCode() == ord('V'):
            return
        elif evt.ControlDown() and evt.GetRawKeyCode() == ord('A') and self.can_select_all:
            self.SelectAll()
        else:
            evt.Skip()

    def _on_paint_col_header_cell(self, grid_col:int, cell_rect: wx.Rect, dc: wx.DC):
        self._on_paint_sort_filter_header(grid_col, cell_rect, dc)
        if self.on_paint_col_header_cell:
            self.on_paint_col_header_cell(grid_col, cell_rect, dc)

    def _on_paint_col_header(self, evt: wx.PaintEvent):
        w: wx.Window = self.GetGridColLabelWindow()
        dc: wx.DC = wx.PaintDC(w)
        pt = dc.GetDeviceOrigin()
        x, y = self.CalcUnscrolledPosition((0, 0))
        dc.SetDeviceOrigin(pt.x - x, pt.y)
        changed_region: wx.Region = w.GetUpdateRegion()
        changed_rect: wx.Rect = changed_region.GetBox()
        changed_rect.SetX(x + changed_rect.GetX())
        changed_rect.SetY(changed_rect.GetY())
        col_height = self.GetColLabelSize()
        prev_col_width = 0

        col_order = []
        for i in range(self.GetNumberCols()):
            col = self.GetColAt(i)
            col_order.append(col)

        for grid_col in col_order:
            cur_col_width = self.GetColSize(grid_col)
            if cur_col_width==0:
                continue
            cell_rect = wx.Rect(prev_col_width, 0, cur_col_width, col_height)
            if cell_rect.Intersects(changed_rect):
                self._on_paint_col_header_cell(grid_col, cell_rect, dc)
            prev_col_width += cur_col_width
        #w.Refresh()
        evt.Skip()

    def _on_paint_sort_filter_header(self, grid_col: int, rect: wx.Rect, dc: wx.DC):

        bitmap_x_offset = rect.GetX()
        if grid_col<0:
            return
        sort_direction = self.table.get_column_info(grid_col).sort_direction
        if  sort_direction!= BTSortOrder.NONE:
            bitmap = None
            if sort_direction  == BTSortOrder.ASCENDING:
                bitmap = self.bitmaps['sort_asc']
            elif sort_direction  == BTSortOrder.DESCENDING:
                bitmap = self.bitmaps['sort_desc']
            if bitmap:
                bitmap_y = int((rect.GetHeight() - bitmap.GetHeight())/2)
                bitmap.SetMaskColour(wx.WHITE)
                dc.DrawBitmap(bitmap, bitmap_x_offset, bitmap_y, useMask=True)
                bitmap_x_offset += bitmap.GetWidth()

        if self.table.get_column_info(grid_col).filter_value is not None:
            bitmap = self.bitmaps['filter']
            bitmap.SetMaskColour(wx.WHITE)
            bitmap_y = int((rect.GetHeight() - bitmap.GetHeight()) / 2)
            dc.DrawBitmap(bitmap, bitmap_x_offset, bitmap_y, useMask=True)

    def _on_paint_row_header_cell(self, grid_row:int, cell_rect: wx.Rect, dc: wx.DC):
        if self.on_paint_row_header_cell:
            self.on_paint_row_header_cell(grid_row, cell_rect, dc)

    def _on_paint_row_header(self, _evt: wx.PaintEvent):
        w1: wx.Window = self.GetGridRowLabelWindow()
        dc1 = wx.PaintDC(w1)
        pt = dc1.GetDeviceOrigin()
        x, y = self.CalcUnscrolledPosition((0, 0))
        dc1.SetDeviceOrigin(pt.x, pt.y - y)

        row_width = self.GetRowLabelSize()
        prev_row_height = 0
        changed_region: wx.Region = w1.GetUpdateRegion()
        changed_rect: wx.Rect = changed_region.GetBox()
        changed_rect.SetX(changed_rect.GetX())
        changed_rect.SetY(y + changed_rect.GetY())
        row_order = []

        for row_i in range(self.GetNumberRows()):
            row = self.GetRowAt(row_i)
            row_order.append(row)

        for row in row_order:
            cur_row_height = self.GetRowSize(row)
            if cur_row_height == 0:
                continue
            cell_rect = wx.Rect(0, prev_row_height, row_width, cur_row_height)
            if cell_rect.Intersects(changed_rect):
                self._on_paint_row_header_cell(row, cell_rect, dc1)
            prev_row_height += cur_row_height
        _evt.Skip()


    def _on_destroy(self, event: wx.WindowDestroyEvent):
        if event.GetEventObject() != self:
            event.Skip()
            return
        for i in range(self.GetNumberRows()):
            self.SetRowAttr(i, None)

        for i in range(self.GetNumberCols()):
            self.SetColAttr(i, None)
        mlogger.debug(f'Destroyed {self}')


    def _on_col_resize(self, evt: wx.grid.GridSizeEvent):
        col = evt.GetRowOrCol()
        self.table.get_column_info(col).width = self.GetColSize(col)
        if self._col_popup_wnd is not None:
            self._col_popup_wnd.Close()
        self.Refresh()
        evt.Skip()

    def _on_col_move(self, evt: wx.grid.GridEvent):
        """ событие происходит с началом переноса """
        # фактическое расположение столбцов будет в текущих значениях только после окончания выполнения этой функции
        col_number = evt.GetCol()
        old_order = []
        for col in range(self.GetNumberCols()):
            old_order.append(self.GetColAt(col))
        wx.CallAfter(self._on_col_move_finished, col_number, old_order)
        evt.Skip()

    def _on_col_move_finished(self, grid_col: int, old_order: List[int]):
        new_order = []
        for col in range(self.GetNumberCols()):
            new_order.append(self.GetColAt(col))
        new_pos = new_order.index(grid_col)
        old_pos = old_order.index(grid_col)
        table_order = self.table.get_columns_order()
        table_order.insert(new_pos, table_order.pop(old_pos))
        self.SetColumnsOrder([i for i in range(self.GetNumberCols())])
        self.table.set_columns_order(table_order)

        for i in range(self.GetNumberCols()):
            self.SetColSize(i, self.table.get_column_info(i).width)
        wx.CallAfter(self.table.on_col_order_changed)

    def _on_row_resize(self, evt: wx.grid.GridSizeEvent):

        row = evt.GetRowOrCol()
        self.table.get_row_info(row).height = self.GetRowSize(row)

        if self._col_popup_wnd is not None:
            self._col_popup_wnd.Close()
        self.Refresh()
        evt.Skip()

    def _on_row_move(self, evt: wx.grid.GridEvent):
        old_order = []
        row_number = evt.GetCol() # глюк wxWidgets - evt.GetRow возвращает неверный индекс перемещяемого объекта а GetCol - верный
        for row in range(self.GetNumberRows()):
            old_order.append(self.GetRowAt(row))

        wx.CallAfter(self._on_row_move_finished, row_number, old_order)
        evt.Skip()

    def _on_row_move_finished(self, grid_row: int, old_order: List[int]):
        new_order = []
        for row in range(self.GetNumberRows()):
            new_order.append(self.GetRowAt(row))
        new_pos = new_order.index(grid_row)
        old_pos = old_order.index(grid_row)
        #table_order = self.table.get_rows_order()
        #table_order.insert(new_pos, table_order.pop(old_pos))
        #self.SetRowsOrder([i for i in range(self.GetNumberRows())])
        self.table.move_row(old_pos, new_pos)
        self.SetRowsOrder([i for i in range(self.GetNumberRows())])
        self.update_row_sizes()
        self.Refresh()
        self.Update()

    def update_row_sizes(self):
        for i in range(self.GetNumberRows()):
            self.SetRowSize(i, self.table.get_row_info(i).height)

    def update_col_sizes(self):
        for i in range(self.GetNumberCols()):
            self.SetColSize(i, self.table.get_column_info(i).width)

    def _on_label_click(self, evt: wx.grid.GridEvent):


        click_col: int = evt.GetCol()
        evt.Skip()


        if click_col>=0:
            popup_x_pos = self.GetRowLabelSize()
            for g_col in range(self.GetNumberCols()):
                if g_col == click_col:
                    break
                popup_x_pos += self.GetColSize(g_col)

            popup_position: wx.Point = self.ClientToScreen(wx.Point(popup_x_pos, self.GetColLabelSize()))
            relative_coords: wx.Point = self.CalcScrolledPosition(popup_position)
            popup_position = wx.Point(relative_coords.Get()[0], popup_position.Get()[1])
            can_sort = self.table.get_column_info(click_col).can_sort
            can_filter = BTFilterType.NONE not in self.table.get_column_info(click_col).allowed_filters


            if can_sort or can_filter:
                if self._col_popup_wnd:
                    self._col_popup_wnd.Dismiss()
                    self._col_popup_wnd = None
                if self._col_popup_wnd is None:
                    busy = wx.IsBusy()
                    if not busy:
                        wx.BeginBusyCursor()
                    frozen = self.IsFrozen()
                    if not frozen:
                        self.Freeze()
                    self._col_popup_wnd = SortFilterPopupWnd(self, click_col)
                    self._col_popup_wnd.SetPosition(popup_position)
                    if not busy:
                        wx.EndBusyCursor()
                    if not frozen:
                        self.Thaw()

                self._col_popup_wnd.Popup()
                self._col_popup_wnd.Update()
                #evt.Veto()

        #click_position = self.ClientToScreen(evt.GetPosition())
        #click_position: wx.Point = self.CalcScrolledPosition(click_position)


    def _on_label_rclick(self, evt: wx.grid.GridEvent):
        clicked_col: int = evt.GetCol()
        clicked_row: int = evt.GetRow()
        click_position = self.ClientToScreen(evt.GetPosition())
        click_position: wx.Point = self.CalcScrolledPosition(click_position)
        self._on_header_click(clicked_row, clicked_col, click_position, False, True, self)
        evt.Skip()
        evt.Skip()

    def _on_header_click(self, _click_row: int, _click_col: int, _pos: wx.Point, _lclick: bool, _rclick: bool, _grid: 'BasicGrid'):
        """Событие возникает нажатии правой мыши на ячейку заголовка, где row и col - адрес в грид"""
        self.show_config_dialog(self._parent)

        # noinspection PyMethodMayBeStatic

    def _on_cel_left_click(self, evt: wx.grid.GridEvent):
        position = evt.GetPosition()

        selected_cells = self.get_selected_grid_cells()
        inside_selected = False
        for grid_cell in selected_cells:
            if evt.GetRow() == grid_cell.GetRow() and evt.GetCol() == grid_cell.GetCol():
                inside_selected = True
                break
        act_cell: wx.grid.GridCellCoords = wx.grid.GridCellCoords(evt.GetRow(), evt.GetCol())
        if act_cell.GetRow() >=0 and act_cell.GetCol()>=0:
            if act_cell not in selected_cells:
                selected_cells.append(act_cell)
        self.on_click_cell(position, selected_cells, True, False, False, inside_selected, self)
        evt.Skip()

    def _on_cel_left_dclick(self, evt: wx.grid.GridEvent):
        position = wx.Point(evt.GetPosition()[0], evt.GetPosition()[1])
        selected_cells = self.get_selected_grid_cells()
        inside_selected = False
        for grid_cell in selected_cells:
            if evt.GetRow() == grid_cell.GetRow() and evt.GetCol() == grid_cell.GetCol():
                inside_selected = True
                break
        act_cell: wx.grid.GridCellCoords = wx.grid.GridCellCoords(evt.GetRow(), evt.GetCol())

        if act_cell.GetRow() >=0 and act_cell.GetCol()>=0:
            if act_cell not in selected_cells:
                selected_cells.append(act_cell)
        self.on_click_cell(position, selected_cells, False, False, True, inside_selected, self)
        evt.Skip()

        # noinspection PyMethodMayBeStatic

    def _on_cel_right_click(self, evt: wx.grid.GridEvent):
        position = wx.Point(evt.GetPosition()[0], evt.GetPosition()[1])
        selected_cells = self.get_selected_grid_cells()
        inside_selected = False
        for grid_cell in selected_cells:
            if evt.GetRow() == grid_cell.GetRow() and evt.GetCol() == grid_cell.GetCol():
                inside_selected = True
                break
        act_cell: wx.grid.GridCellCoords = wx.grid.GridCellCoords(evt.GetRow(), evt.GetCol())

        if act_cell.GetRow() >= 0 and act_cell.GetCol() >= 0:
            if act_cell not in selected_cells:
                selected_cells.append(act_cell)
        self.on_click_cell(position, selected_cells, False, True, False, inside_selected, self)
        evt.Skip()

    def on_click_cell(self, _pos: wx.Point, _selected_cells: List[wx.grid.GridCellCoords], _lclick: bool, _rclick: bool, _dclick: bool, _inside_selected: bool, _grid: 'BasicGrid'):
        """событие которое вызывается при нажатии на ячейку"""
        # noinspection PyProtectedMember
        print('on_click not implemented')
        for c in self.table._columns_info:
            print(c.name,end='')
        print('')
        print(self)
        raise NotImplementedError

    def get_selected_grid_rows(self):
        busy = wx.IsBusy()
        if not busy:
            wx.BeginBusyCursor()

        sel_mode = self.GetSelectionMode()
        grid_rows = []
        if sel_mode == wx.grid.Grid.GridSelectRows:
            grid_rows = self.GetSelectedRows()
        else:
            selected_blocks: wx.grid.GridBlocks = self.GetSelectedBlocks()
            block: wx.grid.GridBlockCoords
            for block in selected_blocks:
                for c in range(block.GetBottomRow() - block.GetTopRow()):
                    r = block.GetTopRow() + c
                    if r not in grid_rows:
                        grid_rows.append(r)
            cell: wx.grid.GridCellCoords
            for cell in self.GetSelectedCells():
                if cell.GetRow() not in grid_rows:
                    grid_rows.append(cell.GetRow())
        if not busy:
            wx.EndBusyCursor()
        return grid_rows



    def get_selected_grid_cells(self)->List[wx.grid.GridCellCoords]:

        sel_mode = self.GetSelectionMode()
        #grid_rows = []
        if sel_mode == wx.grid.Grid.GridSelectRows:
            busy = wx.IsBusy()
            if not busy:
                wx.BeginBusyCursor()
            grid_rows = self.GetSelectedRows()
            cells = set() #: List[wx.grid.GridCellCoords] = []
            for gr in grid_rows:
                for col in range(self.GetNumberCols()):
                    #cell = wx.grid.GridCellCoords(gr, col)
                    cells.add((gr, col))
            if not busy:
                wx.EndBusyCursor()
            answ = []
            for i in cells:
                answ.append(wx.grid.GridCellCoords(i[0], i[1]))
            return answ
        else:
            busy = wx.IsBusy()
            if not busy:
                wx.BeginBusyCursor()

            cells = set() #: List[wx.grid.GridCellCoords] = []
            selected_blocks: wx.grid.GridBlocks = self.GetSelectedBlocks()
            block: wx.grid.GridBlockCoords
            for block in selected_blocks:
                top_left_coords: wx.grid.GridCellCoords = block.GetTopLeft()
                bottom_right_coords: wx.grid.GridCellCoords = block.GetBottomRight()
                for col_n in range(top_left_coords.GetCol(), bottom_right_coords.GetCol() + 1):
                    for row_n in range(top_left_coords.GetRow(), bottom_right_coords.GetRow() + 1):
                        item = (row_n, col_n) #wx.grid.GridCellCoords(row_n, col_n)
                        cells.add(item)
            for cell in self.GetSelectedCells():
                cells.add((cell[0], cell[1])) #cell)
            if not busy:
                wx.EndBusyCursor()
            answ = []
            for i in cells:
                answ.append(wx.grid.GridCellCoords(i[0], i[1]))
            return answ



    def get_grid_cell_by_coords(self, point: wx.Point)->Optional[wx.grid.GridCellCoords]:
        unscrolled: wx.Point = self.CalcUnscrolledPosition(point)
        unscrolled = wx.Point(unscrolled.Get()[0] - self.GetRowLabelSize(), unscrolled.Get()[1] - self.GetColLabelSize())
        row = self.YToRow(unscrolled.Get()[1])
        col = self.XToCol(unscrolled.Get()[0])
        if row>=0 and col>=0:
            return wx.grid.GridCellCoords(row, col)
        return None


    def _on_selection_changed(self, evt: wx.grid.GridRangeSelectEvent):
        #grid_rows = self.get_selected_grid_rows()
        self.on_selection_changed()
        evt.Skip()



    def on_selection_changed(self):
        """событие которое вызывается при смене выбранной ячейки"""
        print(self)
        raise NotImplementedError


    def on_filters_changed(self):
        """событие которое вызывается при смене фильтров"""
        # noinspection PyProtectedMember
        for c in self.table._columns_info:
            print(c.name,end='')
        print('')
        print(self)
        raise NotImplementedError

    # endregion

    # region Наследуемые функции

    def GetNumberRows(self):
        """ Число строк в таблице """
        return self.table.GetNumberRows()

    def GetNumberCols(self):
        """ Число столбцов в таблице """
        return self.table.GetNumberCols()


    # endregion
