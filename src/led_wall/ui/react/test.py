from nicegui import ui
from nicegui_react import React


with ui.card():
    ui.label('Here is the React component:')
    ui.button('Click me', on_click=lambda: react.props(title="Updated Title"))

    with ui.card_section():
        react = React(
            react_project_path=".",
            main_component="App"  # Replace with your main component's name
        ).style('width: 100%; height: 100%;').props(
            title="Hello from Python!"
        ).on('onClick', lambda event: ui.notify(f'Clicked on React component: {event}'))


ui.run(
    title='Led Wall',
    host="0.0.0.0",
    #window_size=(1800, 600),
    dark=True
)