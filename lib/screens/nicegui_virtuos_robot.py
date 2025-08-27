from dotenv import load_dotenv
import os
import json
from lib.services import remote
from lib.services import Virtuos_tool
from nicegui import ui
import asyncio

skip_write_back_in_virtuos = None

def show_virtuos_robot():
    with ui.card().classes('w-full'):
        ui.label("Virtuos Robot Control")
        # Add your UI elements and logic here