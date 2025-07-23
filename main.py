from nicegui import ui
from lib.screens.nicegui_twincat import show_twincat_page

@ui.page('/')
def index():
    ui.label("Main Menu").classes("text-2xl")
    ui.link("TwinCAT Page", "/twincat")

@ui.page("/twincat")
def page_twincat():
    show_twincat_page() 

ui.run()
