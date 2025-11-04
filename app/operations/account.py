"""Account and friend-related operations extracted from OperationsManager."""

from __future__ import annotations

from .account_lib.ports import _get_main_and_sub_ports
from .account_lib.main_device import (
    _load_main_device_data,
    _perform_main_device_login,
)
from .account_lib.sub_devices import (
    _process_sub_devices,
    _initialize_sub_devices,
    _setup_sub_accounts,
    _setup_single_sub_account,
)
from .account_lib.account_creation import (
    _wait_for_account_name_simple,
    _execute_account_creation_steps,
    _input_account_name_fast,
    _confirm_account_creation_fast,
    _complete_initial_quest_fast,
    _wait_for_account_name_screen,
    _input_account_name,
    _execute_sub_terminal_friend_approval,
    _execute_main_terminal_final_confirmation,
    _confirm_account_creation,
    _complete_initial_quest,
)
from .account_lib.friend_flow import (
    _wait_for_room_via_login,
    _execute_friend_registration,
    _execute_main_terminal_friend_processing,
    _execute_sequential_friend_processing,
    _execute_single_sub_friend_processing,
    _wait_for_room_screen,
)
from .account_lib.entrypoints import (
    main_friend_registration,
    main_new_save,
)

__all__ = [
    '_get_main_and_sub_ports',
    '_load_main_device_data',
    '_perform_main_device_login',
    '_process_sub_devices',
    '_initialize_sub_devices',
    '_setup_sub_accounts',
    '_setup_single_sub_account',
    '_wait_for_account_name_simple',
    '_execute_account_creation_steps',
    '_input_account_name_fast',
    '_confirm_account_creation_fast',
    '_complete_initial_quest_fast',
    '_wait_for_room_via_login',
    '_execute_friend_registration',
    '_execute_main_terminal_friend_processing',
    '_execute_sequential_friend_processing',
    '_execute_single_sub_friend_processing',
    '_wait_for_room_screen',
    '_wait_for_account_name_screen',
    '_input_account_name',
    '_execute_sub_terminal_friend_approval',
    '_execute_main_terminal_final_confirmation',
    '_confirm_account_creation',
    '_complete_initial_quest',
    'main_friend_registration',
    'main_new_save',
]
