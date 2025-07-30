from nicegui import ui
from lib.screens.nicegui_twincat_manual_test import show_twincat_manual_page
from lib.screens.nicegui_virtuos_opcua import show_virtuos_server
from lib.screens.nicegui_twincat_manual import show_twincat_page

with ui.tabs().classes('w-full') as tabs:
    twincat_tab = ui.tab('TwinCAT Page')
    virtuos_tab = ui.tab('Virtuos Server Page')
    twincat_tab_test = ui.tab('TwinCAT Manual Test Page')
    

with ui.tab_panels(tabs, value=twincat_tab).classes('w-full'):
    with ui.tab_panel(twincat_tab_test):
        show_twincat_manual_page()

    with ui.tab_panel(virtuos_tab):
        show_virtuos_server()

    with ui.tab_panel(twincat_tab):
        show_twincat_page()

ui.run()
