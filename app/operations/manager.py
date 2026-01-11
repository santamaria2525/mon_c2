 # -*- coding: utf-8 -*-
"""Business logic operations for Monster Strike Bot.

This module handles:
- Device operations and workflows
- Multi-device coordination
- File operations and data management
- Core business logic functions.
"""

import os
import sys
import time
import threading
import openpyxl
import pyautogui
import concurrent.futures
from typing import List, Callable, Optional, Dict, Any

from config import select_ports, host_ports, sub_ports, get_config, get_ports_by_count, MAX_FOLDER_LIMIT
from utils import (
    get_resource_path,
    display_message,
    get_target_folder,
    create_mm_folders,
    get_mm_folder_status,
    clean_mm_folders,
    batch_rename_folders_csv,
    batch_rename_folders_excel,
    close_windows_by_title,
    close_nox_error_dialogs,
)



def _try_stop_task_monitor() -> None:
    """Docstring removed."""
    try:
        from utils.process_task_monitor import stop_process_task_monitor as _stop
    except Exception:
        return
    try:
        _stop()
    except Exception:
        pass

from adb_utils import (
    close_monster_strike_app, start_monster_strike_app,
    remove_data10_bin_from_nox, pull_file_from_nox, run_adb_command,
    reset_adb_server
)
from device_operations import device_operation_select
from login_operations import device_operation_login
from logging_util import MultiDeviceLogger
from monst.device import device_operation_quest
from missing_functions import (
    device_operation_excel_and_save, device_operation_nobin,
    continue_hasya, load_macro
)
from monst.device.hasya import (
    device_operation_hasya, device_operation_hasya_wait, device_operation_hasya_fin,
    device_operation_hasya_host_fin, continue_hasya_parallel, continue_hasya,
    continue_hasya_with_base_folder
)
from utils import find_next_set_folders
from logging_util import logger
from .helpers import (
    run_push,
    run_loop,
    run_loop_enhanced,
    remove_all_nox,
    run_in_threads,
    log_folder_result,
    debug_log,
    find_and_click_with_protection,
    write_account_folders,
)

MAX_PARALLEL_DEVICE_TASKS = 8  # Maximum parallel device tasks
MACRO_MENU_WINDOW_TITLES = (
    "NOX Macro Tool",
    "MSTools Dialog",
)

from . import account as account_ops
from image_detection import tap_if_found_on_windows
from app.core import ApplicationCore
from app_crash_recovery import ensure_app_running, check_app_crash

class OperationsManager:
    """Docstring removed."""
    
    def __init__(self, core: ApplicationCore):
        self.core = core
        #                                            
        config = get_config()
        self.use_independent_processing = config.use_independent_processing
        
        #                   
        self._task_monitor_started = False
        #                          
        self._device_count_logged = False
        self._port_last_started: Dict[str, float] = {}
        self._port_throttle_seconds = 4.0
    
    def set_processing_mode(self, independent: bool = True) -> None:
        """Enable/disable independent processing mode."""
        self.use_independent_processing = independent
        mode_name = "independent" if independent else "shared"
        logger.debug("Processing mode set to %s", mode_name)
    
    def get_processing_mode(self) -> bool:
        """Docstring removed."""
        return self.use_independent_processing

    def _handle_folder_limit_exceeded(self, folder_value: int, *, reason: str | None = None) -> None:
        """Docstring removed."""
        if reason == "no_data":
            logger.info(f"BIN data missing; stopping at folder {folder_value:03d}")
        else:
            logger.error(f"Folder limit exceeded (> {MAX_FOLDER_LIMIT}): {folder_value}")
        logger.info("Folder limit reached. Shutting down application.")
        try:
            _try_stop_task_monitor()
        except Exception:
            pass
        try:
            self.core.stop_event.set()
        except Exception:
            pass
        raise SystemExit(0)

    def _cleanup_macro_windows(self) -> int:
        """Docstring removed."""

        closed = 0
        for title in MACRO_MENU_WINDOW_TITLES:
            closed += close_windows_by_title(title)
        return closed

    def _get_validated_ports(self) -> Optional[List[str]]:
        """Docstring removed."""
        try:
            # config.json                                         
            config = get_config()
            device_count = config.device_count
            
            #             
            from config import validate_device_count
            if not validate_device_count(device_count):
                logger.error(f"?                    {device_count}")
                logger.debug("?? config.json    device_count   -8                    ")
                return None
            
            selected_ports = get_ports_by_count(device_count)
            #                             
            if not self._device_count_logged:
                logger.debug(f"?                  {device_count}  ")
                logger.debug(f"???           {len(selected_ports)}  {selected_ports[:3]}...")
                self._device_count_logged = True
            
            return selected_ports
            
        except Exception as e:
            logger.error(f"?                   : {e}")
            logger.debug("?? config.json    device_count                   ")
            return None
    
    def _get_dynamic_host_sub_ports(self, all_ports: List[str]) -> tuple[List[str], List[str]]:
        """Split NOX ports into host/sub groups."""
        # mon6         4(62028)      8(62032)
        host_port_numbers = ['62028', '62032']  #     4  8
        
        host_ports = []
        sub_ports = []
        
        for port in all_ports:
            port_number = port.split(':')[-1]  # 127.0.0.1:62028 -> 62028
            if port_number in host_port_numbers:
                host_ports.append(port)
            else:
                sub_ports.append(port)
        
        logger.debug(f"??               on6               {len(host_ports)}   /         {len(sub_ports)}  ")
        logger.debug(f"            : {[p.split(':')[-1] for p in host_ports]} (    4,8)")
        logger.debug(f"           : {[p.split(':')[-1] for p in sub_ports]} (    1,2,3,5,6,7)")
        
        return host_ports, sub_ports
    
    def _run_multi_device_operation_mon6(self, op: Callable, ports: List[str], name: str) -> None:
        """Docstring removed."""
        from logging_util import MultiDeviceLogger
        ml = MultiDeviceLogger(ports)
        worker_count = min(len(ports), MAX_PARALLEL_DEVICE_TASKS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
            fs = [exe.submit(op, p, ml) for p in ports]
            
            #                     
            done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
            
            #                       
            for future in done:
                try:
                    result = future.result()
                    logger.debug(f"? {name}         {result}")
                except Exception as e:
                    logger.error(f"? {name}         {e}")
        
        ml.summarize_results(name)
    
    def _run_loop_wrapper(
        self,
        operation: Callable[..., Any],
        operation_name: str,
        ports: List[str],
        *,
        additional_operation: Optional[Callable[[int], Any]] = None,
        custom_args: Optional[Dict[str, Any]] = None,
        save_data_files: bool = False,
        use_independent_processing: Optional[bool] = None,
        base_folder: Optional[int] = None,
    ) -> None:
        """Docstring removed."""
        if base_folder is None:
            base_folder = self.core.get_start_folder()
            if base_folder is None:
                return
        closed = self._cleanup_macro_windows()
        if closed:
            logger.debug("Closed %d leftover macro windows", closed)
        close_nox_error_dialogs()
        reset_adb_server()

        if use_independent_processing is None:
            use_independent_processing = self.use_independent_processing

        ports = [port for port in ports if port]
        if not ports:
            logger.warning("%s: no available device ports", operation_name)
            return

        now = time.time()
        wait_time = 0.0
        for port in ports:
            last = self._port_last_started.get(port, 0.0)
            if last:
                cooldown = self._port_throttle_seconds - (now - last)
                if cooldown > wait_time:
                    wait_time = cooldown
        if wait_time > 0.5:
            wait_time = min(wait_time, self._port_throttle_seconds)
            logger.debug("%s: waiting %.1fs to stagger device start", operation_name, wait_time)
            time.sleep(wait_time)

        ordered_ports = sorted(ports, key=lambda p: self._port_last_started.get(p, 0.0))
        logger.debug(
            "%s: starting loop (mode=%s) on ports %s",
            operation_name,
            'independent' if use_independent_processing else 'cooperative',
            ordered_ports,
        )

        next_base, should_stop = run_loop_enhanced(
            base_folder,
            operation,
            ordered_ports,
            operation_name,
            additional_operation=additional_operation,
            custom_args=custom_args,
            save_data_files=save_data_files,
            use_independent_processing=use_independent_processing,
        )

        stamp = time.time()
        for idx, port in enumerate(ordered_ports):
            self._port_last_started[port] = stamp + idx * 0.5

        if should_stop:
            stop_reason = "no_data" if next_base is None else None
            cutoff_folder = next_base if next_base is not None else max(base_folder, MAX_FOLDER_LIMIT)
            self._handle_folder_limit_exceeded(cutoff_folder, reason=stop_reason)


    def run_multi_device_operation(self, op: Callable, ports: List[str], name: str, folder: str = None) -> None:
        """Docstring removed."""
        #                   
        self._start_task_monitor(ports)
        
        ml = MultiDeviceLogger(ports)
        
        #                                      
        for port in ports:
            folder_str = folder if folder else "---"
            ml.update_task_status(port, folder_str, f"{name}     ")
        
        worker_count = min(len(ports), MAX_PARALLEL_DEVICE_TASKS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
            if folder is not None:
                # folder                     
                fs = [exe.submit(self._execute_with_monitoring, op, p, folder, ml, name) for p in ports]
            else:
                # folder                     
                fs = [exe.submit(self._execute_with_monitoring, op, p, None, ml, name) for p in ports]
            
            #                     
            done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
            
            #                         
            for future in done:
                try:
                    result = future.result()
                    logger.debug(f"? {name}         {result}")
                except Exception as e:
                    logger.error(f"? {name}         {e}")
        
        #                            
        for port in ports:
            folder_str = folder if folder else "---"
            ml.update_task_status(port, folder_str, f"{name} 完了")
        
        ml.summarize_results(name)
    
    # ================== Main Operations ==================
    
    def main_loop_select(self) -> None:
        """Docstring removed."""
        try:
            # config.json                                         
            config = get_config()
            device_count = config.device_count
            
            #             
            from config import validate_device_count
            if not validate_device_count(device_count):
                logger.error(f"?                    {device_count}")
                logger.debug("?? config.json    device_count   -8                    ")
                return
            
            selected_ports = get_ports_by_count(device_count)
            #                             
            if not self._device_count_logged:
                logger.debug(f"?                  {device_count}  ")
                logger.debug(f"???           {len(selected_ports)}  {selected_ports[:3]}...")
                self._device_count_logged = True
            
            #                   
            self._start_task_monitor(selected_ports)
            self._run_loop_wrapper(
                device_operation_select,
                "select",
                selected_ports,
                custom_args={"home_early": True},
            )
            
        except Exception as e:
            logger.error(f"?                      : {e}")
            logger.debug("?? config.json    device_count                   ")
    
    def main_1set(self) -> None:
        """Docstring removed."""
        #                
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        #                                       
        self._start_task_monitor(selected_ports)
        
        #                           
        base_folder = get_target_folder()
        if base_folder is None:
            logger.error("No folder was selected.")
            return
        
        try:
            base_int = int(base_folder)
        except ValueError:
            logger.error(f"                 : {base_folder}")
            return
        
        if base_int > MAX_FOLDER_LIMIT:
            self._handle_folder_limit_exceeded(base_int)
        
        logger.debug(f"1set                       {base_int:03d}   ")
        reset_adb_server()
        run_push(base_int, selected_ports)
        
        # 1set            login           older                      
        ml = MultiDeviceLogger(selected_ports)
        worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
            fs = [exe.submit(device_operation_login, p, str(base_int), ml) for p in selected_ports]
            
            #                     
            done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
            
            #                         
            for future in done:
                try:
                    result = future.result()
                    logger.debug(f"? 1set                         {result}")
                except Exception as e:
                    logger.error(f"? 1set                         {e}")
        
        ml.summarize_results("1set        ")
        logger.debug("1set login processing completed.")
        time.sleep(5)  #            
    
    def main_loop(self, start_folder: Optional[int] = None) -> None:
        """Docstring removed."""
        try:
            # config.json                                         
            config = get_config()
            device_count = config.device_count
            
            #             
            from config import validate_device_count
            if not validate_device_count(device_count):
                logger.error(f"?                    {device_count}")
                logger.debug("?? config.json    device_count   -8                    ")
                return
            
            selected_ports = get_ports_by_count(device_count)
            #                             
            if not self._device_count_logged:
                logger.debug(f"?                  {device_count}  ")
                logger.debug(f"???           {len(selected_ports)}  {selected_ports[:3]}...")
                self._device_count_logged = True
            
            #                   
            self._start_task_monitor(selected_ports)
            
            base_folder = start_folder or get_target_folder()
            if base_folder is None:
                logger.error("No folder was selected.")
                return
            
            try:
                base_int = int(base_folder)
            except ValueError:
                logger.error(f"                 : {base_folder}")
                return
            
            if base_int > MAX_FOLDER_LIMIT:
                self._handle_folder_limit_exceeded(base_int)
            
            logger.debug(f"                          {base_int:03d}    ")
            reset_adb_server()
            custom_args = {'home_early': True}
            
            #                        
            logger.debug(f"??           {'            if self.use_independent_processing else '          }")
            
            next_folder, should_stop = run_loop_enhanced(
                base_int, device_operation_login, selected_ports, "Login",
                custom_args=custom_args,
                use_independent_processing=self.use_independent_processing
            )

            # BIN data exhaustion or upper limit triggers a controlled shutdown
            if should_stop:
                stop_reason = "no_data" if next_folder is None else None
                cutoff_folder = next_folder if next_folder is not None else max(base_int, MAX_FOLDER_LIMIT)
                self._handle_folder_limit_exceeded(cutoff_folder, reason=stop_reason)

            if next_folder:
                logger.debug(f"               : {next_folder:03d}")
                
        except Exception as e:
            logger.error(f"?                         : {e}")
            logger.debug("?? config.json    device_count                   ")
    
    def main_loop_stop(self) -> None:
        """Docstring removed."""
        #                
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        #                                       
        self._start_task_monitor(selected_ports)
        
        #                           
        base_folder = get_target_folder()
        if base_folder is None:
            logger.error("No folder was selected.")
            return
        
        try:
            base_int = int(base_folder)
        except ValueError:
            logger.error(f"                 : {base_folder}")
            return
        
        if base_int > MAX_FOLDER_LIMIT:
            self._handle_folder_limit_exceeded(base_int)
        
        logger.debug(f"8                        {base_int:03d}   ")
        
        # 8                          
        from utils.set_processing import run_continuous_set_loop
        from adb_utils import reset_adb_server
        
        reset_adb_server()
        
        try:
            run_continuous_set_loop(
                base_folder=base_int,
                operation=device_operation_login,
                ports=selected_ports,
                operation_name="            8             ",
                custom_args=None,
                summary_label="ログイン",
            )
        except Exception as e:
            logger.error(f"8                  : {e}")
            display_message("      ", f"                         : {e}")
    
    def main_loop_hasya(self) -> None:
        """Docstring removed."""
        #                                 +               
        
        #                                  
        current_folder_base = None
        processed_folders = set()  #                              
        
        def add_ops(current_folder: int):
            nonlocal current_folder_base, processed_folders
            current_folder_base = current_folder
            processed_folders.clear()
            block_start = current_folder_base
            
            #                rocessed_folders                 
            initial_range = set(range(current_folder, current_folder + 8))
            logger.debug(f"??                   : {sorted(initial_range)}")
            
            #                          
            from memory_monitor import memory_monitor, force_cleanup
            memory_monitor.cleanup_aggressive_mode = True
            memory_monitor.consecutive_critical_count = 0
            memory_monitor.check_interval = 30  # 30              
            logger.debug("??                                     ")
            
            #                       
            force_cleanup()
            
            #                            
            import psutil
            memory_percent = psutil.virtual_memory().percent
            logger.debug(f"??                     : {memory_percent:.1f}%")
            
            # ===========================================
            #                        bin                   
            # ===========================================
            logger.debug("Bin push: base folder %s (8 devices)", current_folder_base)
            
            #              
            selected_ports = self._get_validated_ports()
            if selected_ports is None:
                logger.error("?   [                             ")
                return
            device_count = len(selected_ports)
            
            #    bin                            
            from mon_c2.multi_device import run_push
            try:
                run_push(current_folder_base, selected_ports)
                logger.debug(f"?    bin                           {current_folder_base}~{current_folder_base+7}")
            except Exception as e:
                logger.error(f"?    bin                    {e}")
                raise
            
            # bin                      
            time.sleep(3)
            logger.debug("Bin push completed; waiting before sets")
            
            #           = 2           
            for set_number in range(1, 3):  # 1                
                logger.debug("Set %s start at %s", set_number, time.strftime("%Y-%m-%d %H:%M:%S"))
                
                #                                     
                import psutil
                memory_percent = psutil.virtual_memory().percent
                available_mb = psutil.virtual_memory().available / (1024 * 1024)
                
                logger.debug(f"??      {set_number}                {memory_percent:.1f}% (        : {available_mb:.0f}MB)")
                
                if memory_percent >= 98.0:
                    logger.error("Set %s memory critical: %.1f%%", set_number, memory_percent)
                    #            
                    force_cleanup()
                    memory_monitor._extreme_cleanup()
                    time.sleep(3)
                elif memory_percent >= 95.0:
                    logger.warning("Set %s memory high: %.1f%%", set_number, memory_percent)
                    force_cleanup()
                    time.sleep(2)
                
                #                   
                new_memory_percent = psutil.virtual_memory().percent
                if new_memory_percent >= 97.0:
                    logger.warning("Set %s memory still high after cleanup: %.1f%%", set_number, new_memory_percent)
                    memory_monitor.consecutive_critical_count += 1
                
                # ===========================================
                #                                         +          
                # ===========================================
                
                if set_number == 1:
                    # 1                   
                    set1_folders = set(range(current_folder_base, current_folder_base + 8))
                    logger.debug(f"                       {sorted(set1_folders)}                   ..")
                    
                    #                                
                    processed_folders.update(set1_folders)
                    logger.debug(f"??                   : {sorted(processed_folders)}")
                    selected_ports = self._get_validated_ports()
                    if selected_ports is None:
                        logger.error("?                     ")
                        return
                    
                    # 1                                               
                    import concurrent.futures
                    from login_operations import device_operation_login
                    from monst.logging import MultiDeviceLogger
                    
                    ml = MultiDeviceLogger(selected_ports)
                    worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
                        fs = [exe.submit(device_operation_login, p, str(current_folder_base + i), ml) 
                              for i, p in enumerate(selected_ports)]
                        
                        #                     
                        done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
                        
                        #                       
                        for future in done:
                            try:
                                result = future.result()
                                logger.debug(f"? 1                        {result}")
                            except Exception as e:
                                logger.error(f"? 1                        {e}")
                    
                    ml.summarize_results("           8            ")
                    logger.debug("Set 1 login completed for 8 devices")
                    time.sleep(5)  #                    
                    
                    # 1                                       8          
                    logger.info("           :                                         ..")
                    
                    #                                                            
                    ml2 = MultiDeviceLogger(selected_ports)
                    worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
                        #                        
                        fs = [exe.submit(self._execute_hasya_quest_preparation, p, str(current_folder_base + i), ml2) 
                              for i, p in enumerate(selected_ports)]
                        
                        #                     
                        done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
                        
                        #                       
                        for future in done:
                            try:
                                result = future.result()
                                logger.debug(f"? 1                       {result}")
                            except Exception as e:
                                logger.error(f"? 1                       {e}")
                    
                    ml2.summarize_results("                      ")
                    logger.debug("Set 1 app prep completed; waiting")
                    time.sleep(8)  #                               
                    
                elif set_number == 2:
                    # 2             8                                
                    previous_base = current_folder_base
                    current_folder_base = current_folder_base + 8
                    
                    #                          
                    set2_folders = set(range(current_folder_base, current_folder_base + 8))
                    duplicate_check = set2_folders.intersection(processed_folders)
                    if duplicate_check:
                        logger.error("Duplicate folders detected: %s", sorted(duplicate_check))
                        raise ValueError(f"                : {sorted(duplicate_check)}")
                    
                    logger.debug("Set 2 base moved: %s -> %s", previous_base, current_folder_base)
                    logger.debug("Set 2 folders: %s (prev=%s-%s)", sorted(set2_folders), previous_base, previous_base + 7)
                    
                    #                                
                    processed_folders.update(set2_folders)
                    logger.debug(f"??                   : {sorted(processed_folders)}")
                    
                    # ===========================================
                    #                               bin                   
                    # ===========================================
                    logger.debug("Bin push: base folder %s (set 2)", current_folder_base)
                    
                    selected_ports = self._get_validated_ports()
                    if selected_ports is None:
                        logger.error("?                     ")
                        return
                    
                    # 2           bin                            
                    from mon_c2.multi_device import run_push
                    try:
                        run_push(current_folder_base, selected_ports)
                        logger.debug(f"? 2       bin                           {current_folder_base}~{current_folder_base+7}")
                    except Exception as e:
                        logger.error(f"? 2       bin                    {e}")
                        raise
                    
                    # bin                      
                    time.sleep(3)
                    logger.debug("Set 2 bin push completed; waiting")
                    
                    # 2              8                                
                    logger.info("                8                     ..")
                    selected_ports = self._get_validated_ports()
                    
                    # 8                                          
                    import concurrent.futures
                    from login_operations import device_operation_login
                    from monst.logging import MultiDeviceLogger
                    
                    ml = MultiDeviceLogger(selected_ports)
                    worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
                        fs = [exe.submit(device_operation_login, p, str(current_folder_base + i), ml) 
                              for i, p in enumerate(selected_ports)]
                        
                        #                     
                        done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
                        
                        #                       
                        for future in done:
                            try:
                                result = future.result()
                                logger.debug(f"?                  {result}")
                            except Exception as e:
                                logger.error(f"?                  {e}")
                    
                    ml.summarize_results("           8            ")
                    logger.debug("Set 2 login completed for 8 devices")
                    time.sleep(5)  #                         
                    
                    #                               8          
                    logger.info("           :                                         ..")
                    from monst.device.hasya import device_operation_hasya
                    
                    #                                                            
                    ml2 = MultiDeviceLogger(selected_ports)
                    worker_count = min(len(selected_ports), MAX_PARALLEL_DEVICE_TASKS)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
                        #                                                                     
                        fs = [exe.submit(self._execute_hasya_quest_preparation, p, str(current_folder_base + i), ml2) 
                              for i, p in enumerate(selected_ports)]
                        
                        #                     
                        done, _ = concurrent.futures.wait(fs, return_when=concurrent.futures.ALL_COMPLETED)
                        
                        #                       
                        for future in done:
                            try:
                                result = future.result()
                                logger.debug(f"?                 {result}")
                            except Exception as e:
                                logger.error(f"?                 {e}")
                    
                    ml2.summarize_results("                      ")
                    logger.debug("Set 2 app prep completed; waiting")
                    time.sleep(8)  #                               
                
                #                                      
                #                                          
                logger.debug("Hasya set %s: preparing follow-up", set_number)
                time.sleep(3)  #                       
                continue_hasya_with_base_folder(current_folder_base)
                
                # mon6  host_ports/sub_ports   
                from config import select_ports
                selected_ports = self._get_validated_ports()
                device_count = len(selected_ports)
                dynamic_host_ports, dynamic_sub_ports = self._get_dynamic_host_sub_ports(selected_ports)
                
                # mon6                                          
                #                                            
                logger.debug("Hasya wait: set %s start (8 devices)", set_number)
                self._run_multi_device_operation_mon6(device_operation_hasya_wait, dynamic_host_ports, f"Hasya wait set {set_number}")
                logger.debug("Hasya wait: set %s completed", set_number)
                
                #                 8                  on6                    
                logger.debug("Hasya: set %s start (8 devices)", set_number)
                
                # OK                    
                for i in range(3):
                    tap_if_found_on_windows("tap", "ok.png", "macro")
                    time.sleep(2)  # 1   2       
                    
                # 8                        
                from utils.gui_dialogs import multi_press_enhanced
                multi_press_enhanced()
                
                #                         
                for i in range(8):
                    tap_if_found_on_windows("tap", "macro_fin.png", "macro")
                    time.sleep(2)  # 1   2       
                
                set_start_folder = int(current_folder_base)
                set_end_folder = set_start_folder + device_count - 1
                logger.info("Set %s range: %03d-%03d", set_number, set_start_folder, set_end_folder)
                
                logger.debug("Set %s completed", set_number)
                
                # 1                  in        2                       
                if set_number == 1:
                    logger.debug("Short delay before set 2")
                    time.sleep(2)  #                
            
            #   2            QWERASDF          on6        
            block_end = block_start + device_count * 2 - 1
            logger.info("Block range %03d-%03d (2 sets)", block_start, block_end)
            logger.debug("              QWERASDF          ..")
            time.sleep(2)  #                     
            
            from utils.gui_dialogs import multi_press_enhanced
            multi_press_enhanced()
            
            # monst_macro                                           
            logger.debug("              monst_macro                ..")
            for i in range(8):
                tap_if_found_on_windows("tap", "macro_fin.png", "macro")
                time.sleep(2)  # 1   2                              
            
            #                                      
            memory_monitor.cleanup_aggressive_mode = False
            memory_monitor.consecutive_critical_count = 0
            memory_monitor.check_interval = 60  #              
            
            #                    
            final_memory_percent = psutil.virtual_memory().percent
            final_available_mb = psutil.virtual_memory().available / (1024 * 1024)
            logger.debug(f"??                                             ")
            logger.debug(f"??                 {final_memory_percent:.1f}% (        : {final_available_mb:.0f}MB)")
            
            #                                        
            if final_memory_percent >= 85.0:
                logger.debug("Post-cycle cleanup triggered")
                force_cleanup()
            
            next_base_candidate = current_folder_base + 8
            _, next_folders = find_next_set_folders(next_base_candidate, device_count)
            if next_folders and len(next_folders) == device_count:
                next_start = int(next_folders[0])
                next_end = int(next_folders[-1])
                logger.info(f"                        {next_start:03d}-{next_end:03d}")
                add_ops(next_start)
                return
            logger.info("No more sets available")
        
        # ===================
        #                                       
        # ===================
        
        #                
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        #                   
        self._start_task_monitor(selected_ports)
        
        #                           
        base_folder = get_target_folder()
        if base_folder is None:
            logger.error("No folder was selected.")
            return
        
        try:
            base_int = int(base_folder)
        except ValueError:
            logger.error(f"                 : {base_folder}")
            return
        
        if base_int > MAX_FOLDER_LIMIT:
            self._handle_folder_limit_exceeded(base_int)
        
        logger.debug(f"                        {base_int:03d}   ")
        
        from adb_utils import reset_adb_server
        reset_adb_server()
        
        #                   
        add_ops(base_int)
    
    def _execute_hasya_quest_preparation(self, device_port: str, folder: str, multi_logger: Optional[MultiDeviceLogger] = None) -> bool:
        """Prepare a device for the Hasya quest flow."""
        try:
            from monst.image import tap_if_found, tap_until_found

            logger.debug(f"                   {device_port} (       {folder})")

            while True:
                if tap_if_found('stay', device_port, "start.png", "quest"):
                    if not tap_if_found('stay', device_port, "dekki_null2.png", "key"):
                        break
                tap_if_found('tap', device_port, "quest_c.png", "key")
                tap_if_found('tap', device_port, "quest.png", "key")
                tap_if_found('tap', device_port, "ichiran.png", "key")
                tap_if_found('tap', device_port, "ok.png", "key")
                tap_if_found('tap', device_port, "close.png", "key")

                hasya_images = [
                    "hasyatou.png",
                    "hasyatou2.png",
                    "hasyatou3.png",
                    "hasyatou4.png",
                    "hasyatou5.png",
                    "hasyatou6.png",
                ]
                for hasya_img in hasya_images:
                    tap_if_found('tap', device_port, hasya_img, "key")

                tap_if_found('tap', device_port, "shohi20.png", "key")
                tap_if_found('tap', device_port, "minnato.png", "key")
                tap_if_found('tap', device_port, "multi.png", "key")

                if tap_if_found('stay', device_port, "dekki_null2.png", "key"):
                    tap_until_found(device_port, "go_tittle.png", "key", "sonota.png", "key", "tap")
                    tap_until_found(device_port, "date_repear.png", "key", "go_tittle.png", "key", "tap")
                    tap_until_found(device_port, "data_yes.png", "key", "date_repear.png", "key", "tap")
                    tap_until_found(device_port, "zz_home.png", "key", "data_yes.png", "key", "tap")

                time.sleep(2)

            suffixes = ('62025', '62026', '62027', '62029', '62030', '62031')
            if device_port.endswith(suffixes):
                tap_if_found('tap', device_port, "zz_home.png", "key")

            logger.debug(f"                   {device_port} (       {folder})")
            if multi_logger:
                multi_logger.log_success(device_port)
            return True

        except Exception as e:
            error_msg = f"Login operation failed: {str(e)} (folder={folder})"
            logger.error(error_msg, exc_info=True)
            if multi_logger:
                multi_logger.log_error(device_port, error_msg)
            return False
    def main_single(self) -> None:
        """Docstring removed."""
        logger.info("Single-device mode selected.")
        
        try:
            #                
            available_ports = [
                '127.0.0.1:62025', '127.0.0.1:62026', '127.0.0.1:62027',
                '127.0.0.1:62028', '127.0.0.1:62029', '127.0.0.1:62030',
                '127.0.0.1:62031', '127.0.0.1:62032'
            ]
            
            port = None
            try:
                port = self.core.select_device_port()
            except Exception:
                pass
            
            # GUI                                 
            if port is None:
                print("\nSelect a device port:")
                print("Enter number or 0 to cancel.")
                for i, available_port in enumerate(available_ports, 1):
                    print(f"  {i}. {available_port}")
                
                while True:
                    try:
                        choice = input(f"\n                       (1-{len(available_ports)}, 0=          ): ").strip()
                        
                        if choice == "0":
                            return
                        
                        if choice == "":
                            port = available_ports[0]
                            break
                            
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(available_ports):
                            port = available_ports[choice_num - 1]
                            break
                        else:
                            print(f"Please enter a number between 1 and {len(available_ports)}.")
                            
                    except (ValueError, KeyboardInterrupt):
                        print("Invalid input. Try again.")
                        continue
            
            if port is None:
                return
            
            #                
            base = self.core.get_start_folder()
            if base is None:
                return
            
            #                     
            src = get_resource_path(f"{str(base).zfill(3)}/data10.bin", "bin_push")
            if src is None or not os.path.exists(src):
                error_msg = f"       {base:03d}  data10.bin                    "
                logger.error(error_msg)
                display_message("      ", error_msg)
                return
            
            #         
            reset_adb_server()
            close_monster_strike_app(port)
            run_adb_command(['push', src, "/data/data/jp.co.mixi.monsterstrike/data10.bin"], port)
            start_monster_strike_app(port)
            
            #                        
            if not ensure_app_running(port):
                logger.error(f"                      (      {port})")
                display_message("Error", "App is not running on the selected port.")
                return
            
            #                 
            device_operation_login(port, str(base).zfill(3))
            
            #                     
            if check_app_crash(port):
                logger.warning(f"                    (      {port})")
            
            #     
            logger.info("                            ")
                
        except Exception as e:
            error_msg = f"                                     : {e}"
            logger.error(error_msg)
            display_message("Error", f"{error_msg}\n\nSee logs for details.")
            return
    
    def main_single_del(self) -> None:
        """Docstring removed."""
        logger.info("Single-device delete mode selected.")
        
        try:
            #                
            available_ports = [
                '127.0.0.1:62025', '127.0.0.1:62026', '127.0.0.1:62027',
                '127.0.0.1:62028', '127.0.0.1:62029', '127.0.0.1:62030',
                '127.0.0.1:62031', '127.0.0.1:62032'
            ]
            
            port = None
            try:
                port = self.core.select_device_port()
            except Exception:
                pass
            
            # GUI                                 
            if port is None:
                print("\nSelect a device port:")
                print("Enter number or 0 to cancel.")
                for i, available_port in enumerate(available_ports, 1):
                    print(f"  {i}. {available_port}")
                
                while True:
                    try:
                        choice = input(f"\n                       (1-{len(available_ports)}, 0=          ): ").strip()
                        
                        if choice == "0":
                            return
                        
                        if choice == "":
                            port = available_ports[0]
                            break
                            
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(available_ports):
                            port = available_ports[choice_num - 1]
                            break
                        else:
                            print(f"Please enter a number between 1 and {len(available_ports)}.")
                            
                    except (ValueError, KeyboardInterrupt):
                        print("Invalid input. Try again.")
                        continue
            
            if port is None:
                return
            
            #         
            reset_adb_server()
            close_monster_strike_app(port)
            remove_data10_bin_from_nox(port)
            start_monster_strike_app(port)
            
            #     
            logger.info("                        ")
            
        except Exception as e:
            error_msg = f"                                  : {e}"
            logger.error(error_msg)
            display_message("Error", f"{error_msg}\n\nSee logs for details.")
            return
    
    def main_single_save(self) -> None:
        """Docstring removed."""
        logger.info("                      ..")
        
        try:
            #                
            available_ports = [
                '127.0.0.1:62025', '127.0.0.1:62026', '127.0.0.1:62027',
                '127.0.0.1:62028', '127.0.0.1:62029', '127.0.0.1:62030',
                '127.0.0.1:62031', '127.0.0.1:62032'
            ]
            
            port = None
            try:
                port = self.core.select_device_port()
            except Exception as gui_error:
                logger.warning(f"GUI         : {gui_error}")
            
            if port is None:
                print("\n===             -                ===")
                print("                      ")
                for i, available_port in enumerate(available_ports, 1):
                    print(f"  {i}. {available_port}")
                
                while True:
                    try:
                        choice = input(f"\n                       (1-{len(available_ports)}, 0=          ): ").strip()
                        
                        if choice == "0":
                            print("Cancelled.")
                            return
                        
                        if choice == "":
                            port = available_ports[0]
                            break
                            
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(available_ports):
                            port = available_ports[choice_num - 1]
                            break
                        else:
                            print(f"Please enter a number between 1 and {len(available_ports)}.")
                            
                    except (ValueError, KeyboardInterrupt):
                        print("Invalid input. Try again.")
                        continue
            
            if port is None:
                logger.error("                             ")
                return
            
            #                 
            save_folder = None
            try:
                save_folder = get_target_folder()
                if save_folder:
                    save_folder = save_folder.strip()
            except Exception:
                pass
            
            if not save_folder:
                print("\n                            :")
                while True:
                    try:
                        save_folder = input("         (    =single, 0=          ): ").strip()
                        
                        if save_folder == "0":
                            return
                        
                        if save_folder == "":
                            save_folder = "single"
                            break
                        
                        if any(char in save_folder for char in '<>:"/\\|?*'):
                            print("Invalid folder name.")
                            continue
                        
                        break
                        
                    except KeyboardInterrupt:
                        return
            
            if not save_folder:
                save_folder = "single"
            
            # ADB              
            reset_adb_server()
            
            #                          
            success = pull_file_from_nox(port, save_folder)
            
            #          
            from utils import get_base_path
            import os
            
            save_dir = os.path.join(get_base_path(), "bin_pull", save_folder)
            save_file = os.path.join(save_dir, "data10.bin")
            
            if os.path.exists(save_file) and os.path.getsize(save_file) > 0:
                logger.debug(f"                 {port} -> {save_folder}")
            else:
                logger.error("                             ")
                
        except Exception as e:
            error_msg = f"                                 : {e}"
            logger.error(error_msg)
            display_message("Error", f"{error_msg}\n\nSee logs for details.")
            return
    
    
    
    
    
    
    
    
    
    
    
    
    
    
            
            
    
    
    
    
    
    
    
    
    

    
    def main_no_bin(self) -> None:
        """Docstring removed."""
        #                
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        #                                       
        self._start_task_monitor(selected_ports)
        self._run_loop_wrapper(device_operation_nobin, "no bin", selected_ports)
    
    def main_id_check(self) -> None:
        """Docstring removed."""
        from monst.device.operations import id_check
        from utils.clipboard_manager import register_device_for_clipboard
        
        #                
        ports = self._get_validated_ports()
        if ports is None:
            return
        
        #                                                         
        for i, device_port in enumerate(ports):
            register_device_for_clipboard(device_port, i)
        
        #                   
        self._start_task_monitor(ports)
        
        logger.info("ID_Check start.")
        
        ml = MultiDeviceLogger(ports)
        
        #         ID         
        worker_count = min(len(ports), MAX_PARALLEL_DEVICE_TASKS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as exe:
            futures = []
            for i, device_port in enumerate(ports):
                if self.core.is_stopping():
                    break
                    
                folder = f"{i+1:03d}"  #                    
                
                #                            
                ml.update_task_status(device_port, folder, "ID_check     ")
                
                # ID              
                future = exe.submit(self._execute_id_check_with_monitoring, 
                                  device_port, folder, ml)
                futures.append(future)
            
            #                      
            concurrent.futures.wait(futures)
        
        #                            
        for i, device_port in enumerate(ports):
            folder = f"{i+1:03d}"
            ml.update_task_status(device_port, folder, "ID_check done")
        
        ml.summarize_results("ID_Check")
        logger.info("ID_Check completed.")
    
    def _execute_id_check_with_monitoring(self, device_port: str, folder: str, 
                                        multi_logger: MultiDeviceLogger) -> None:
        """Docstring removed."""
        try:
            from monst.device.operations import id_check
            
            multi_logger.update_task_status(device_port, folder, "ID_check  ")
            
            player_id = id_check(device_port, folder, multi_logger)
            
            if player_id and "COMPLETED" in player_id:
                multi_logger.log_success(device_port)
                multi_logger.update_task_status(device_port, folder, "ID_check   ")
            else:
                multi_logger.log_error(device_port, "ID check failed")
                multi_logger.update_task_status(device_port, folder, "ID_check failed")
                
        except Exception as e:
            multi_logger.log_error(device_port, str(e))
            multi_logger.update_task_status(device_port, folder, "ID_check      ")
    
    def main_macro(self) -> None:
        """Docstring removed."""
        base = get_target_folder()
        if base is None:
            logger.warning("No macro was selected.")
            return

        try:
            macro_number = int(base)
        except ValueError:
            logger.error(f"           : {base}")
            display_message("Error", "Invalid macro number.")
            return

        self._cleanup_macro_windows()

        try:
            load_macro(macro_number)
        finally:
            closed = self._cleanup_macro_windows()
            if closed:
                logger.info("Closed %s stray macro menu window(s)", closed)

    def main_loop_event(self) -> None:
        """Docstring removed."""
        #                
        selected_ports = self._get_validated_ports()
        if selected_ports is None:
            return
            
        #                                       
        self._start_task_monitor(selected_ports)
        self._run_loop_wrapper(device_operation_quest, "Quest", selected_ports)
    
    def monitor_check(self) -> None:
        """Docstring removed."""
        logger.info("Monitor check started.")
        logger.info("NOX status check started.")
    
    # ================== MM Folder Operations ==================
    
    def mm_folder_split(self) -> None:
        """Docstring removed."""
        logger.info("MM folder split started.")
        try:
            stats = create_mm_folders()
            total = sum(stats.values())
            if total > 0:
                #             
                result_details = []
                for mm_number, count in stats.items():
                    if count > 0:
                        result_details.append(f"{mm_number}: {count}       ")
                
                result_text = f"MM              n\n      : {total}       \n\n" + "\n".join(result_details)
                display_message("MM Result", result_text)
            else:
                display_message("    ", "bin_push                                          ")
                logger.warning("No MM folders were created.")
        except Exception as e:
            logger.error(f"MM                : {e}")
            display_message("      ", f"MM                      \n\n          :\n{e}")
    
    def mm_folder_batch_rename(self) -> None:
        """Docstring removed."""
        import tkinter as tk
        from tkinter import filedialog
        
        logger.info("MM batch rename started.")
        
        try:
            # Excel                    
            root = tk.Tk()
            root.withdraw()  #                     
            root.lift()
            root.attributes('-topmost', True)
            
            #           folder_change.xlsx     
            default_excel = os.path.join(os.getcwd(), "folder_change.xlsx")
            initial_dir = os.path.dirname(default_excel) if os.path.exists(default_excel) else os.getcwd()
            initial_file = "folder_change.xlsx" if os.path.exists(default_excel) else ""
            
            excel_path = filedialog.askopenfilename(
                title="         Excel                     ",
                filetypes=[("Excel files", "*.xlsx"), ("Excel files (old)", "*.xls"), ("CSV files", "*.csv"), ("All files", "*.*")],
                defaultextension=".xlsx",
                initialdir=initial_dir,
                initialfile=initial_file
            )
            
            root.destroy()
            
            if not excel_path:
                logger.info("Excel                              ")
                return
            
            #                                  
            file_extension = os.path.splitext(excel_path)[1].lower()
            if file_extension in ['.xlsx', '.xls']:
                # Excel             
                results = batch_rename_folders_excel(excel_path)
                file_type = "Excel"
            elif file_extension == '.csv':
                # CSV                          
                results = batch_rename_folders_csv(excel_path)
                file_type = "CSV"
            else:
                display_message("      ", f"                               {file_extension}")
                return
            
            if not results:
                display_message("      ", f"{file_type}                             ")
                return
            
            #        
            success_count = sum(1 for success in results.values() if success)
            fail_count = len(results) - success_count
            
            if success_count > 0:
                #             
                success_list = [folder for folder, success in results.items() if success]
                fail_list = [folder for folder, success in results.items() if not success]
                
                result_text = f"                      n\n"
                result_text += f"      : {len(results)}       \n"
                result_text += f"   : {success_count}       \n"
                result_text += f"     {fail_count}       \n\n"
                
                if success_count > 0:
                    result_text += "             :\n" + "\n".join(success_list[:10])
                    if len(success_list) > 10:
                        result_text += f"\n... ({len(success_list) - 10} more)"
                
                if fail_count > 0:
                    result_text += "\n\n              :\n" + "\n".join(fail_list[:5])
                    if len(fail_list) > 5:
                        result_text += f"\n... ({len(fail_list) - 5} more)"
                
                result_text += "\n\n             'rename_result'                     "
                
                display_message("Rename Result", result_text)
            else:
                display_message("Rename Result", "No folders were renamed.")
                logger.warning("No folders were renamed.")
                
        except Exception as e:
            logger.error(f"                        : {e}")
            display_message("      ", f"                              \n\n          :\n{e}")
    
    def _start_task_monitor(self, ports: list[str]) -> None:
        """Docstring removed."""
        logger.debug('Task monitor disabled; skipping startup.')


    def _execute_with_monitoring(self, operation: Callable, device_port: str, folder: str, 
                                multi_logger: MultiDeviceLogger, operation_name: str) -> None:
        """Docstring removed."""
        try:
            folder_str = folder if folder else "---"
            multi_logger.update_task_status(device_port, folder_str, f"{operation_name}  ")
            
            if folder is not None:
                operation(device_port, folder, multi_logger)
            else:
                operation(device_port, multi_logger)
                
            multi_logger.log_success(device_port)
        except Exception as e:
            multi_logger.log_error(device_port, str(e))
            folder_str = folder if folder else "---"
            multi_logger.update_task_status(device_port, folder_str, f"{operation_name}      ")






# Bind account-related helpers to OperationsManager
OperationsManager._get_main_and_sub_ports = account_ops._get_main_and_sub_ports
OperationsManager._load_main_device_data = account_ops._load_main_device_data
OperationsManager._perform_main_device_login = account_ops._perform_main_device_login
OperationsManager._process_sub_devices = account_ops._process_sub_devices
OperationsManager._initialize_sub_devices = account_ops._initialize_sub_devices
OperationsManager._setup_sub_accounts = account_ops._setup_sub_accounts
OperationsManager._setup_single_sub_account = account_ops._setup_single_sub_account
OperationsManager._wait_for_account_name_simple = account_ops._wait_for_account_name_simple
OperationsManager._execute_account_creation_steps = account_ops._execute_account_creation_steps
OperationsManager._input_account_name_fast = account_ops._input_account_name_fast
OperationsManager._confirm_account_creation_fast = account_ops._confirm_account_creation_fast
OperationsManager._complete_initial_quest_fast = account_ops._complete_initial_quest_fast
OperationsManager._wait_for_room_via_login = account_ops._wait_for_room_via_login
OperationsManager._execute_friend_registration = account_ops._execute_friend_registration
OperationsManager._execute_main_terminal_friend_processing = account_ops._execute_main_terminal_friend_processing
OperationsManager._execute_sequential_friend_processing = account_ops._execute_sequential_friend_processing
OperationsManager._execute_single_sub_friend_processing = account_ops._execute_single_sub_friend_processing
OperationsManager._wait_for_account_name_screen = account_ops._wait_for_account_name_screen
OperationsManager._input_account_name = account_ops._input_account_name
OperationsManager._execute_sub_terminal_friend_approval = account_ops._execute_sub_terminal_friend_approval
OperationsManager._execute_main_terminal_final_confirmation = account_ops._execute_main_terminal_final_confirmation
OperationsManager._confirm_account_creation = account_ops._confirm_account_creation
OperationsManager._complete_initial_quest = account_ops._complete_initial_quest
OperationsManager._wait_for_room_screen = account_ops._wait_for_room_screen
OperationsManager.main_friend_registration = account_ops.main_friend_registration
OperationsManager.main_new_save = account_ops.main_new_save
