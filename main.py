from nicegui import ui
from lib.screens.nicegui_twincat import show_twincat_page
from lib.screens.nicegui_virtuos_opcua import show_virtuos_server

with ui.tabs().classes('w-full') as tabs:
    twincat_tab = ui.tab('TwinCAT Page')
    virtuos_tab = ui.tab('Virtuos Server Page')

with ui.tab_panels(tabs, value=twincat_tab).classes('w-full'):
    with ui.tab_panel(twincat_tab):
        show_twincat_page()

    with ui.tab_panel(virtuos_tab):
        show_virtuos_server()

ui.run()
