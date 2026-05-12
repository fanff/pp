#!/usr/bin/env python3

import asyncio
import datetime
import json
import os
import re
import uuid
from time import time
from types import NoneType
from typing import List

import websockets
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    ContentSwitcher,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    RichLog,
    Rule,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
    Tree,
    Welcome,
)
from textual.widgets._tree import TreeNode

from ppback.ppschema import MessageWS
from ppback.thedummyclient import PPClient


class UserCreationForm(Static):
    """Form for creating a new user."""

    def __init__(self):
        super().__init__()
        self.username_input = Input(placeholder="Username", restrict=r"^[a-zA-Z0-9_]+$")
        self.password_input = Input(
            placeholder="Password", password=True, restrict=r"^[a-zA-Z0-9_!@#$%^&*()]*$"
        )
        self.password_confirm_input = Input(
            placeholder="Confirm Password",
            password=True,
            restrict=r"^[a-zA-Z0-9_!@#$%^&*()]*$",
        )
        self.email_input = Input(placeholder="Email")
        self.submit_button = Button("Create User", id="submit_user_creation")
        self.restrict_email_regex = r"^[\w.-]+@[\w.-]+\.[a-zA-Z]{2,}$"
        self.error_message = Static("", id="error_message", classes="error-message")

        self.border_title = "Create New User"

    def compose(self) -> ComposeResult:
        """Compose the form elements."""
        yield self.username_input
        yield self.password_input
        yield self.password_confirm_input
        yield self.email_input

        yield self.error_message
        yield self.submit_button

    def get_user_input_data(self):
        """Get the user input data from the form."""
        # Ensure passwords match
        if self.password_input.value != self.password_confirm_input.value:
            self.error_message.update("Passwords do not match")
            return None

        # Ensure passwords is at lease 8 characters long
        if len(self.password_input.value) < 8:
            self.error_message.update("Password must be at least 8 characters long")
            return None

        # Ensure email is valid
        if not re.match(self.restrict_email_regex, self.email_input.value):
            self.error_message.update("Invalid email address")
            return None

        self.error_message.update("")  # Clear any previous error message

        return {
            "username": self.username_input.value,
            "password": self.password_input.value,
            "email": self.email_input.value,
        }


class AdminApp(App):
    """Main application class for the admin interface."""

    CSS_PATH = "pp.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the UI components."""
        yield Header()
        yield UserCreationForm()
        yield Footer()

    async def on_button_pressed(self, event) -> None:
        """Handle button press events."""
        if event.button.id == "submit_user_creation":
            user_data = event.button.parent.get_user_input_data()
            if user_data is None:
                return

            try:
                # Attempt to create the user
                await self.create_user(user_data)
            except ValueError as e:
                pass

    async def create_user(self, user_data):
        """Create a new user."""
        # TODO


if __name__ == "__main__":
    app = AdminApp()
    app.run()
