from nicegui import ui
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from client.session_api import SessionAPI
from client.phoebe_api import PhoebeAPI
from ui.utils import time_to_phase, alias_data, flux_to_magnitude


class PhoebeParameterWidget:
    """Widget for a single Phoebe parameter with value, adjustment checkbox, and step size."""

    def __init__(self, name: str, label: str, value: float, step: float = 0.001,
                 adjust: bool = False, phoebe_api=None, on_value_changed=None):
        self.name = name  # This should be the Phoebe twig
        self.label = label
        self.value = value
        self.step = step
        self.adjust = adjust
        self.phoebe_api = phoebe_api  # Reference to API for setting values
        self.on_value_changed = on_value_changed  # Optional callback for UI updates

        with ui.row().classes('items-center gap-2 w-full'):
            # Parameter label
            ui.label(f'{label}:').classes('w-24 flex-shrink-0 text-sm')

            # Value input
            self.value_input = ui.number(
                label='Value',
                value=value,
                format='%.6f',
                step=step
            ).classes('flex-1 min-w-0')

            # Add value change handler
            def handle_change():
                self._on_value_changed(self.value_input.value)
            self.value_input.on('update:model-value', handle_change)

            # Checkbox for adjustment (moved before step)
            self.adjust_checkbox = ui.checkbox(text='Adjust', value=adjust).classes('flex-shrink-0')
            self.adjust_checkbox.on('update:model-value', self._on_adjust_changed)

            # Step size input (after checkbox)
            self.step_input = ui.number(
                label='Step',
                value=step,
                format='%.6f',
                step=step/10
            ).classes('flex-1 min-w-0')

            # Set initial state of step input
            self._on_adjust_changed()

    def _on_adjust_changed(self):
        """Handle adjust checkbox state change."""
        if self.adjust_checkbox.value:
            self.step_input.enable()
            self.step_input.classes(remove='text-gray-400')
        else:
            self.step_input.disable()
            self.step_input.classes(add='text-gray-400')

    def _on_value_changed(self, new_value):
        """Handle parameter value changes by updating Phoebe bundle and calling optional callback."""
        if new_value is None:
            return

        # Update the stored value
        self.value = new_value

        # Call API to set the value in Phoebe
        if self.phoebe_api:
            try:
                response = self.phoebe_api.set_value(self.name, new_value)
                if response.get('status') == 'success':
                    # Successful update - could add debug notification if needed
                    pass
                else:
                    ui.notify(f'Failed to set {self.name}: {response.get("error", "Unknown error")}', type='negative')
            except Exception as e:
                ui.notify(f'Error setting {self.name}: {str(e)}', type='negative')

        # Call optional callback for additional UI updates
        if self.on_value_changed:
            self.on_value_changed(self.name, new_value)


class DatasetModel:
    def __init__(self, api):
        self.api = api
        self.datasets = {}

        # Define a dataset model:
        self.model = {
            'kind': 'lc',
            'dataset': f'ds{len(self.datasets) + 1}',
            'passband': 'Johnson:V',
            'times': [],
            'fluxes': [],
            'model_fluxes': [],
            'rv1s': [],
            'rv2s': [],
            'model_rv1s': [],
            'model_rv2s': [],
            'sigmas': [],
            'filename': '',
            'n_points': 201,
            'phase_min': -0.5,
            'phase_max': 0.5,
            'data_points': 0,
            'plot_data': False,
            'plot_model': False
        }

    def add(self, **kwargs):
        kind = kwargs.pop('kind', None)
        dataset = kwargs.pop('dataset', None)

        if not kind:
            raise ValueError('Dataset kind not specified.')

        if not dataset:
            raise ValueError('Dataset label not specified.')

        if dataset in self.datasets:
            raise ValueError(f'Dataset {dataset} already exists -- please choose a unique label.')

        dataset_meta = self.model.copy()

        dataset_meta.update({
            'kind': kind,
            'dataset': dataset,
            **kwargs
        })

        self.datasets[dataset] = dataset_meta

        compute_phases = np.linspace(
            dataset_meta['phase_min'],
            dataset_meta['phase_max'],
            dataset_meta['n_points']
        )

        # Call API to add the dataset:
        params = {
            'dataset': dataset_meta.get('dataset'),
            'passband': dataset_meta.get('passband', 'Johnson:V'),
            'compute_phases': compute_phases,
            'times': dataset_meta.get('times', []),
            'sigmas': dataset_meta.get('sigmas', [])
        }
        if kind == 'lc':
            params['fluxes'] = dataset_meta.get('fluxes', [])
        if kind == 'rv':
            params['rv1s'] = dataset_meta.get('rv1s', [])
            params['rv2s'] = dataset_meta.get('rv2s', [])

        self.api.add_dataset(kind, **params)

        # set pblum_mode to dataset-scaled if we have actual data:
        if len(dataset_meta['fluxes']) > 0 or len(dataset_meta['rv1s']) > 0 or len(dataset_meta['rv2s']) > 0:
            self.api.set_value(f'pblum_mode@{dataset}', 'dataset-scaled')

    def remove(self, dataset):
        if dataset not in self.datasets:
            raise ValueError(f'Dataset {dataset} does not exist.')

        self.api.remove_dataset(dataset)
        del self.datasets[dataset]


class PhoebeUI:
    """Main Phoebe UI."""

    def __init__(self, session_api: SessionAPI = None, phoebe_api: PhoebeAPI = None):
        self.session_api = session_api
        self.phoebe_api = phoebe_api
        self.client_id = None  # Will be set when session is established
        self.user_first_name = None
        self.user_last_name = None

        # Reference to widgets:
        self.widgets = {}

        # Initialize dialogs:
        self.dataset = DatasetModel(api=self.phoebe_api)
        self.dataset_dialog = self.create_dataset_dialog()

        # Show startup dialog first
        self.show_startup_dialog()

        # Create main UI (will be shown after dialog)
        with ui.splitter(value=30).classes('w-full h-screen') as self.main_splitter:
            # Left panel - Parameters, data, and controls
            with self.main_splitter.before:
                with ui.scroll_area().classes('w-full h-full p-4'):
                    self.create_parameter_panel()

            # Right panel - Data, plots and results
            with self.main_splitter.after:
                self.create_analysis_panel()

            # Allow plot width change on splitter drag
            # Handle plot resize on splitter change
            plot_id = self.lc_canvas.id
            plot_resize_js = f'Plotly.Plots.resize(getHtmlElement({plot_id}))'
            self.main_splitter.on_value_change(lambda: ui.run_javascript(plot_resize_js))

    def create_parameter_panel(self):
        # Model selection
        self.model_select = ui.select(
            options={
                'phoebe': 'PHOEBE',
                'phoebai': 'PHOEBAI'
            },
            value='phoebe',
            label='Model'
        ).classes('w-full mb-4')

        self.morphology_select = ui.select(
            options={
                'detached': 'Detached binary',
                'semidetached': 'Semi-detached binary',
                'contact': 'Contact binary'
            },
            value='detached',
            label='Binary star morphology type'
        ).classes('w-full mb-4')
        self.morphology_select.on('update:model-value', self._on_morphology_change)
        self._current_morphology = 'detached'  # Track current morphology

        # Ephemerides parameters
        with ui.expansion('Ephemerides', icon='schedule', value=False).classes('w-full mb-4'):
            # Create parameter widgets for t0 and period
            self.t0_param = PhoebeParameterWidget(
                name='t0_supconj@binary',
                label='T₀ (BJD)',
                value=2458000.0,
                step=0.01,
                adjust=False,
                phoebe_api=self.phoebe_api,
                on_value_changed=self.on_ephemeris_changed
            )

            self.period_param = PhoebeParameterWidget(
                name='period@binary',
                label='Period (d)',
                value=2.5,
                step=0.0001,
                adjust=False,
                phoebe_api=self.phoebe_api,
                on_value_changed=self.on_ephemeris_changed
            )

        # Primary star parameters
        with ui.expansion('Primary Star', icon='wb_sunny', value=False).classes('w-full mb-4'):
            self.mass1_param = PhoebeParameterWidget(
                name='mass@primary',
                label='Mass (M₀)',
                value=1.0,
                step=0.01,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

            self.radius1_param = PhoebeParameterWidget(
                name='requiv@primary',
                label='Radius (R₀)',
                value=1.0,
                step=0.01,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

            self.temperature1_param = PhoebeParameterWidget(
                name='teff@primary',
                label='Temperature (K)',
                value=5778.0,
                step=10.0,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

        # Secondary star parameters
        with ui.expansion('Secondary Star', icon='wb_sunny', value=False).classes('w-full mb-4'):
            self.mass2_param = PhoebeParameterWidget(
                name='mass@secondary',
                label='Mass (M₀)',
                value=0.8,
                step=0.01,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

            self.radius2_param = PhoebeParameterWidget(
                name='requiv@secondary',
                label='Radius (R₀)',
                value=0.8,
                step=0.01,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

            self.temperature2_param = PhoebeParameterWidget(
                name='teff@secondary',
                label='Temperature (K)',
                value=4800.0,
                step=10.0,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

        # Orbit parameters
        with ui.expansion('Orbit', icon='trip_origin', value=False).classes('w-full mb-4'):
            self.inclination_param = PhoebeParameterWidget(
                name='incl@binary',
                label='Inclination (°)',
                value=90.0,
                step=0.1,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

            self.eccentricity_param = PhoebeParameterWidget(
                name='ecc@binary',
                label='Eccentricity',
                value=0.0,
                step=0.01,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

            self.omega_param = PhoebeParameterWidget(
                name='per0@binary',
                label='Argument of periastron (°)',
                value=0.0,
                step=1.0,
                adjust=False,
                phoebe_api=self.phoebe_api
            )

    def create_dataset_panel(self):
        with ui.expansion('Dataset Management', icon='table_chart', value=True).classes('w-full mb-2').style('padding: 2px;'):
            # Enhanced dataset control grid
            self.dataset_table = ui.aggrid({
                'columnDefs': [
                    {'field': 'label', 'headerName': 'Dataset', 'width': 120, 'sortable': True},
                    {'field': 'type', 'headerName': 'Type', 'width': 60, 'sortable': True},
                    {'field': 'phases', 'headerName': 'Phases', 'width': 100, 'sortable': True},
                    {'field': 'data_points', 'headerName': 'Data Points', 'width': 90, 'sortable': True, 'type': 'numericColumn'},
                    {'field': 'passband', 'headerName': 'Passband', 'width': 100, 'sortable': True},
                    {'field': 'filename', 'headerName': 'Source', 'width': 120, 'sortable': True},
                    {
                        'field': 'plot_data',
                        'headerName': 'Plot Data',
                        'width': 90,
                        'cellRenderer': 'agCheckboxCellRenderer',
                        ':editable': 'params => { return params.data.filename !== "Synthetic"; }'  # leading colon means js content instead of string
                    },
                    {
                        'field': 'plot_model',
                        'headerName': 'Plot Model',
                        'width': 90,
                        'cellRenderer': 'agCheckboxCellRenderer',
                        'editable': True
                    }
                ],
                'rowData': [],  # start with an empty table
                'domLayout': 'autoHeight',
                'suppressHorizontalScroll': False,
                'enableCellChangeFlash': True,
                'rowSelection': 'single',
                # 'theme': 'ag-theme-alpine'
            }).classes('w-full').style('height: auto; min-height: 80px; max-height: 300px;')

            # Store selected row for edit/remove operations
            self.selected_dataset_row = None

            # Listen to row selections:
            self.dataset_table.on('rowSelected', self.on_dataset_row_selected)

            # Listen to checkbox toggles
            self.dataset_table.on('cellValueChanged', self.on_dataset_panel_checkbox_toggled)

            # Dataset action buttons
            with ui.row().classes('gap-2 justify-end w-full'):
                ui.button(
                    'Add',
                    on_click=self.on_dataset_panel_add_button_clicked,
                    icon='add'
                ).props('flat color=primary')
                ui.button(
                    'Edit',
                    on_click=self.on_dataset_panel_edit_button_clicked,
                    icon='edit'
                ).props('flat color=secondary')
                ui.button(
                    'Remove',
                    on_click=self.on_dataset_panel_remove_button_clicked,
                    icon='delete'
                ).props('flat color=negative')

    def create_compute_panel(self):
        with ui.expansion('Model computation', icon='calculate', value=False).classes('w-full'):

            with ui.column().classes('w-full h-full p-4 min-w-0'):
                with ui.row().classes('gap-4 items-center w-full'):
                    self.compute_button = ui.button(
                        'Compute Model',
                        on_click=self.compute_model,
                        icon='calculate'
                    ).classes('h-12 flex-shrink-0')

    def create_lc_panel(self):
        with ui.expansion('Light curve', icon='insert_chart', value=False).classes('w-full'):

            with ui.column().classes('w-full h-full p-4 min-w-0'):

                # Plot controls row
                with ui.row().classes('gap-4 items-center mb-4'):
                    # X-axis dropdown
                    self.widgets['lc_plot_x_axis'] = ui.select(
                        options={'time': 'Time', 'phase': 'Phase'},
                        value='time',
                        label='X-axis'
                    ).classes('w-24 h-10')
                    self.widgets['lc_plot_x_axis'].on('update:model-value', lambda: self.on_lc_plot_update())

                    # Y-axis dropdown
                    self.widgets['lc_plot_y_axis'] = ui.select(
                        options={'magnitude': 'Magnitude', 'flux': 'Flux'},
                        value='flux',
                        label='Y-axis'
                    ).classes('w-24 h-10')
                    self.widgets['lc_plot_y_axis'].on('update:model-value', lambda: self.on_lc_plot_update())

                    # Plot button, styled for alignment
                    ui.button('Plot', on_click=self.on_lc_plot_button_clicked).classes('bg-blue-500 h-10 translate-y-4')

                # Plot container
                self.lc_canvas = ui.plotly(self.create_empty_styled_lc_plot()).classes('w-full  min-w-0')

                # Add resize observer to handle container size changes
                self.lc_canvas._props['config'] = {
                    'responsive': True,
                    'displayModeBar': True,
                    'displaylogo': False
                }

    def create_fitting_panel(self):
        with ui.expansion('Model fitting', icon='tune', value=False).classes('w-full'):

            with ui.column().classes('h-full p-4 min-w-0'):
                with ui.row().classes('w-full gap-4 mt-2'):
                    # Solver selection
                    self.solver_select = ui.select(
                        options={'dc': 'Differential corrections'},
                        value='dc',
                        label='Solver'
                    ).classes('mb-4')
                
                    self.fit_button = ui.button(
                        'Run solver',
                        on_click=self.fit_parameters,
                        icon='tune'
                    ).classes('h-12 flex-shrink-0')

    def create_empty_styled_lc_plot(self):
        fig = go.Figure()

        x_title = 'Time (BJD)'
        y_title = 'Flux'

        fig.update_layout(
            xaxis_title=x_title,
            yaxis_title=y_title,
            hovermode='closest',
            template='plotly_white',
            autosize=True,
            height=400,
            margin=dict(l=50, r=50, t=50, b=50),
            xaxis=dict(
                mirror='allticks',
                ticks='outside',
                showline=True,
                linecolor='black',
                linewidth=2,
                zeroline=False,
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                griddash='dot'
            ),
            yaxis=dict(
                mirror='allticks',
                ticks='outside',
                showline=True,
                linecolor='black',
                linewidth=2,
                # autorange='reversed' if y_reversed else True,
                zeroline=False,
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                griddash='dot'
            ),
            plot_bgcolor='white',
            showlegend=False,
            uirevision=True
        )

        return fig

    def on_lc_plot_update(self):
        # Handle updates to the light curve plot
        return

    def on_lc_plot_button_clicked(self):
        # We'll redraw the figure from scratch each time.
        fig = self.create_empty_styled_lc_plot()

        period = self.period_param.value
        t0 = self.t0_param.value

        # See what needs to be plotted:
        for ds_label, ds_meta in self.dataset.datasets.items():
            if ds_meta['kind'] == 'lc':
                x_axis = self.widgets['lc_plot_x_axis'].value
                y_axis = self.widgets['lc_plot_y_axis'].value

                if ds_meta['plot_data']:
                    if x_axis == 'time':
                        xs = ds_meta['times']
                    else:
                        xs = time_to_phase(ds_meta['times'], period, t0)

                    if y_axis == 'flux':
                        ys = ds_meta['fluxes']
                    else:
                        ys = flux_to_magnitude(ds_meta['fluxes'])

                    data = np.column_stack((xs, ys))  # we could also add sigmas here

                    # Alias phases:
                    if x_axis == 'phase':
                        data = alias_data(data, extend_range=0.1)

                    fig.add_trace(go.Scatter(
                        x=data[:, 0],
                        y=data[:, 1],
                        mode='markers',
                        name=ds_label
                    ))

                if ds_meta['plot_model']:
                    compute_phases = np.linspace(ds_meta['phase_min'], ds_meta['phase_max'], ds_meta['n_points'])
                    if x_axis == 'time':
                        xs = t0 + period * compute_phases
                    else:
                        xs = compute_phases

                    if y_axis == 'flux':
                        ys = ds_meta['model_fluxes']
                    else:
                        ys = flux_to_magnitude(ds_meta['model_fluxes'])

                    model = np.column_stack((xs, ys))

                    if x_axis == 'phase':
                        model = alias_data(model, extend_range=0.1)

                    fig.add_trace(go.Scatter(
                        x=model[:, 0],
                        y=model[:, 1],
                        mode='lines',
                        line={'color': 'red'},
                        name=ds_label
                    ))

        self.lc_canvas.figure = fig
        self.lc_canvas.update()

    def refresh_dataset_panel(self):
        row_data = []

        for ds_label, ds_meta in self.dataset.datasets.items():
            plot_data = False
            plot_model = False

            # phases string:
            phase_min = ds_meta.get('phase_min')
            phase_max = ds_meta.get('phase_max')
            n_points = ds_meta.get('n_points')
            phases_str = f'({phase_min:.2f}, {phase_max:.2f}, {n_points})'

            row_data.append({
                'label': ds_label,
                'type': ds_meta['kind'],
                'passband': ds_meta['passband'],
                'filename': ds_meta['filename'],
                'phases': phases_str,
                'data_points': ds_meta['data_points'],
                'plot_data': plot_data,
                'plot_model': plot_model
            })

        self.dataset_table.options['rowData'] = row_data
        self.dataset_table.update()

    def create_dataset_dialog(self):
        with ui.dialog() as dialog, ui.card().classes('w-[800px] h-[600px]'):
            title = 'Add Dataset'
            ui.label(title).classes('text-xl font-bold mb-4')

            self.data_file = None
            self.data_content = None

            with ui.column().classes('w-full gap-4'):
                self.widgets['dataset_kind'] = ui.select(
                    options={'lc': 'Light Curve', 'rv': 'RV Curve'},
                    # value=dataset_info.get('kind'),
                    label='Dataset type'
                ).classes('w-full')

                self.widgets['dataset_label'] = ui.input(
                    label='Dataset Label',
                    placeholder='e.g., lc01, rv01, etc.',
                ).classes('w-full')

                self.widgets['dataset_passband'] = ui.select(
                    options=['GoChile:R', 'GoChile:G', 'GoChile:B', 'GoChile:L', 'TESS:T', 'Kepler:mean', 'Johnson:V'],
                    label='Passband'
                ).classes('w-full')

                # Phase parameters section in foldable element
                with ui.expansion('Model', icon='straighten', value=False).classes('w-full mt-4'):
                    with ui.row().classes('gap-2 w-full'):
                        self.widgets['dataset_phase_min'] = ui.number(
                            label='Phase min',
                            value=-0.5,
                            step=0.1,
                            format='%.2f'
                        ).classes('flex-1')

                        self.widgets['dataset_phase_max'] = ui.number(
                            label='Phase max',
                            value=0.5,
                            step=0.1,
                            format='%.2f'
                        ).classes('flex-1')

                        self.widgets['dataset_n_points'] = ui.number(
                            label='Length',
                            value=201,
                            min=20,
                            max=10000,
                            step=1,
                            format='%d'
                        ).classes('flex-1')

            ui.separator().classes('my-4')

            with ui.expansion('Observations', icon='insert_chart', value=False).classes('w-full'):
                with ui.tabs().classes('w-full') as tabs:
                    example_tab = ui.tab('Example Files')
                    upload_tab = ui.tab('Upload File')

                with ui.tab_panels(tabs, value=example_tab).classes('w-full'):
                    # Example tab
                    with ui.tab_panel(example_tab):
                        ui.label('Select an example data file:').classes('mb-2')

                        # TODO: move example file location to a config file
                        examples_dir = Path(__file__).parent.parent / 'examples'
                        example_files = []

                        if examples_dir.exists():
                            for file_path in examples_dir.glob('*'):
                                example_files.append({
                                    'name': file_path.name,
                                    'path': str(file_path),
                                    'description': '',
                                    # 'description': self._get_file_description(file_path.name)
                                })

                        if example_files:
                            # Track selected file and cards for highlighting

                            example_cards = []

                            def toggle_card_selection(file_path, card_element):
                                if self.data_file == file_path:
                                    # Deselect
                                    self.data_file = None
                                    card_element.classes(remove='bg-blue-100 border-blue-500 border-2')
                                    card_element.classes(add='bg-white border-gray-200')
                                else:
                                    # Reset all cards first
                                    for other_card in example_cards:
                                        other_card.classes(remove='bg-blue-100 border-blue-500 border-2')
                                        other_card.classes(add='bg-white border-gray-200')

                                    # Select new file
                                    self.data_file = file_path
                                    card_element.classes(remove='bg-white border-gray-200')
                                    card_element.classes(add='bg-blue-100 border-blue-500 border-2')

                            with ui.column().classes('w-full gap-2'):
                                for file_info in example_files:
                                    card_classes = ('cursor-pointer hover:bg-gray-50 p-3 '
                                                    'bg-white border-gray-200 border')
                                    with ui.card().classes(card_classes) as card:
                                        example_cards.append(card)
                                        ui.label(file_info['name']).classes('font-bold')
                                        ui.label(file_info['description']).classes('text-sm text-gray-600')

                                        # Make the entire card clickable with toggle behavior
                                        card.on('click', lambda file_path=file_info['path'], card_el=card:
                                                toggle_card_selection(file_path, card_el))
                        else:
                            ui.label('No example files found').classes('text-gray-500')

                    # Upload tab
                    with ui.tab_panel(upload_tab):
                        ui.label('Upload a data file from your computer:').classes('mb-2')
                        ui.label('Supported formats: Space or tab-separated text '
                                 'files with columns:').classes('text-sm text-gray-600')
                        ui.label('Time, Flux/Magnitude/Velocity, Error').classes('text-sm text-gray-600 mb-4')

                        # File upload
                        file_upload = ui.upload(
                            max_file_size=10_000_000,  # 10MB limit
                            max_files=1,
                            on_upload=self.on_dataset_dialog_file_uploaded,
                        ).classes('w-full')
                        file_upload.classes('border-2 border-dashed border-gray-300 rounded-lg p-8 text-center')

            ui.separator().classes('my-4')

            with ui.row().classes('gap-2 justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).classes('bg-gray-500')
                ui.button(
                    'Add',
                    icon='save',
                    on_click=self.on_dataset_dialog_add_button_clicked
                ).classes('bg-blue-500')

        return dialog

    def on_dataset_dialog_file_uploaded(self, event):
        if event and event.name and event.content:
            self.data_file = event.name
            self.data_content = event.content
            ui.notify(f'File uploaded: {self.data_file}', type='success')
        else:
            ui.notify('File upload failed.', type='error')

    def on_dataset_dialog_add_button_clicked(self):
        param_to_widget = {
            'kind': 'dataset_kind',
            'dataset': 'dataset_label',
            'passband': 'dataset_passband',
            'times': '',
            'fluxes': '',
            'rv1s': '',
            'rv2s': '',
            'sigmas': '',
            'filename': '',
            'n_points': 'dataset_n_points',
            'phase_min': 'dataset_phase_min',
            'phase_max': 'dataset_phase_max',
            'data_points': '',
            'plot_data': '',
            'plot_model': ''
        }

        kind = self.widgets['dataset_kind'].value

        model = self.dataset.model.copy()
        for param, widget in param_to_widget.items():
            if widget and widget in self.widgets:
                model[param] = self.widgets[widget].value

        # Handle observational data if available
        if self.data_file:
            if self.data_content:
                data_content = np.genfromtxt(self.data_content)
            else:
                data_content = np.genfromtxt(self.data_file)

            model['filename'] = self.data_file
            model['data_points'] = len(data_content)
            model['times'] = data_content[:, 0]
            if kind == 'lc':
                model['fluxes'] = data_content[:, 1]
            if kind == 'rv':
                # TODO: fix this.
                model['rv1s'] = data_content[:, 1]
                model['rv2s'] = data_content[:, 1]
            model['sigmas'] = data_content[:, 2]
        else:
            model['filename'] = 'Synthetic'

        try:
            self.dataset.add(**model)
        except Exception as e:
            ui.notify(f'Error adding dataset: {e}', type='error')

        self.refresh_dataset_panel()

        self.dataset_dialog.close()

    def on_dataset_panel_add_button_clicked(self):
        # self.open_dataset_dialog()
        self.dataset_dialog.open()

    def on_dataset_panel_edit_button_clicked(self):
        if not self.selected_dataset_row:
            ui.notify('Please select a dataset to edit.', type='warning')
            return

        self.dataset_dialog.open()
        # TODO: need to populate with dataset=self.selected_dataset_row['label'])

    def on_dataset_panel_remove_button_clicked(self):
        if not self.selected_dataset_row:
            ui.notify('Please select a dataset to remove.', type='warning')
            return

        dataset = self.selected_dataset_row['label']

        with ui.dialog() as dialog, ui.card():
            ui.label(f'Are you sure you want to remove dataset "{dataset}"?').classes('text-lg font-bold')
            with ui.row().classes('gap-2 justify-end mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button(
                    'Remove',
                    on_click=lambda: self.on_dataset_remove_confirmed(dataset, dialog),
                    color='negative'
                ).props('flat')

        dialog.open()

    def on_dataset_remove_confirmed(self, dataset, dialog):
        self.dataset.remove(dataset)
        self.refresh_dataset_panel()
        dialog.close()

    def on_dataset_panel_checkbox_toggled(self, event):
        dataset = event.args['data']['label']
        field = event.args['colId']
        state = event.args['value']

        self.dataset.datasets[dataset][field] = state

    def on_dataset_row_selected(self, event):
        # Selected dataset needs to be kept in the class as an attribute
        # so that nicegui can connect the reference with the requestor.
        # It's certainly tempting to look up the selected row directly,
        # for example by get_selected_row(), but this is async and needs
        # to be awaited and nicegui can't do that because there's no
        # unique reference to the requesting session.

        if event.args and 'data' in event.args and 'label' in event.args['data']:
            self.selected_dataset_row = event.args['data']
        else:
            self.selected_dataset_row = None

    def create_analysis_panel(self):
        with ui.column().classes('w-full h-full p-4 min-w-0'):
            # Dataset management panel:
            self.create_dataset_panel()

            # Compute management panel:
            self.create_compute_panel()

            # Light curve plot (pass reference to UI for parameter access)
            self.create_lc_panel()

            # Fitting panel:
            self.create_fitting_panel()

    def show_startup_dialog(self):
        """Show startup dialog to collect user info and initialize session."""
        with ui.dialog().props('persistent') as self.startup_dialog, ui.card().classes('w-96'):
            ui.label('Welcome to Phoebe UI').classes('text-xl font-bold mb-4')

            # Show client ID (will be populated after session init)
            ui.label('Session ID:').classes('text-sm font-medium')
            self.client_id_display = ui.label('Initializing...').classes('text-sm text-gray-600 mb-4 font-mono')

            ui.separator().classes('my-4')

            # User info form
            ui.label('Please provide your information:').classes('text-sm font-medium mb-2')

            self.first_name_input = ui.input(
                label='First Name',
                placeholder='Enter your first name'
            ).classes('mb-2').props('outlined')

            self.last_name_input = ui.input(
                label='Last Name',
                placeholder='Enter your last name'
            ).classes('mb-4').props('outlined')

            # Buttons
            with ui.row().classes('gap-2 justify-end w-full'):
                ui.button('Continue', on_click=self._on_continue_startup).classes('bg-blue-500').props('unelevated')

        # Open dialog and initialize session
        self.startup_dialog.open()
        self._initialize_session_background()

    def _initialize_session_background(self):
        """Initialize session in the background."""
        # Prevent duplicate session creation
        if self.client_id:
            self.client_id_display.text = self.client_id
            return

        if not self.session_api:
            self.client_id_display.text = 'API not available'
            return

        try:
            # Start a new session
            response = self.session_api.start_session()
            self.client_id = response.get('client_id')

            if self.client_id and self.phoebe_api:
                # Set client ID in Phoebe API
                self.phoebe_api.set_client_id(self.client_id)
                self.client_id_display.text = self.client_id
            else:
                self.client_id_display.text = 'Failed to initialize'

        except Exception as e:
            self.client_id_display.text = f'Error: {str(e)}'

    def _on_continue_startup(self):
        """Handle continue button in startup dialog."""
        first_name = self.first_name_input.value.strip()
        last_name = self.last_name_input.value.strip()

        if not first_name or not last_name:
            ui.notify('Please enter both first and last name', type='warning')
            return

        if not self.client_id:
            ui.notify('Session not ready. Please wait and try again.', type='warning')
            return

        # Store user info
        self.user_first_name = first_name
        self.user_last_name = last_name

        # Update session metadata with user info
        try:
            self.session_api.update_user_info(self.client_id, first_name, last_name)
        except Exception as e:
            ui.notify(f'Warning: Could not update session info: {str(e)}', type='warning')

        # Close dialog and show main UI
        self.startup_dialog.close()
        self.main_splitter.style('display: flex')

        ui.notify(f'Welcome {first_name} {last_name}! Session {self.client_id} ready.', type='positive')

    def cleanup_session(self):
        """Cleanup the current session."""
        if self.client_id and self.session_api:
            try:
                self.session_api.end_session(self.client_id)
                self.session_status.text = 'No session'
                ui.notify(f'Session {self.client_id} ended', type='info')
            except Exception as e:
                ui.notify(f'Error ending session: {str(e)}', type='warning')
            finally:
                self.client_id = None
                if self.phoebe_api:
                    self.phoebe_api.set_client_id(None)

    def on_ephemeris_changed(self, param_name=None, param_value=None):
        """Handle changes to ephemeris parameters (t0, period) and update phase plot."""
        # Only replot if we're currently showing phase on x-axis or if there's any data to plot
        if self.widgets['lc_plot_x_axis'].value == 'phase' or any(
            ds_meta.get('plot_data', False) or ds_meta.get('plot_model', False)
            for ds_meta in self.dataset.datasets.values() if ds_meta['kind'] == 'lc'
        ):
            self.on_lc_plot_button_clicked()

    def _on_morphology_change(self):
        """Handle morphology selection change with confirmation dialog."""
        new_morphology = self.morphology_select.value

        # If it's the same as current, no need to warn
        if new_morphology == self._current_morphology:
            return

        # Show confirmation dialog
        with ui.dialog() as dialog, ui.card():
            ui.label('Warning: Morphology Change').classes('text-lg font-bold mb-4')
            morphology_msg = (f'Changing morphology from "{self._current_morphology}" '
                              f'to "{new_morphology}" will reset all system '
                              f'parameters to their default values.')
            ui.label(morphology_msg)
            ui.label('Do you want to continue?').classes('mb-4')

            with ui.row().classes('gap-4 justify-end w-full'):
                ui.button('Cancel', on_click=lambda: self._cancel_morphology_change(dialog)).classes('bg-gray-500')
                confirm_btn = ui.button('Continue',
                                        on_click=lambda: self._confirm_morphology_change(
                                            dialog, new_morphology))
                confirm_btn.classes('bg-red-500')

        dialog.open()

    def _cancel_morphology_change(self, dialog):
        """Cancel morphology change and revert selection."""
        dialog.close()
        # Revert to previous morphology without triggering callback
        self.morphology_select.value = self._current_morphology
        ui.notify('Morphology change cancelled', type='info')

    def _confirm_morphology_change(self, dialog, new_morphology):
        """Confirm morphology change and reset parameters."""
        dialog.close()
        self._current_morphology = new_morphology
        self._reset_parameters_to_defaults()
        ui.notify(f'Morphology changed to {new_morphology}. Parameters reset to defaults.', type='positive')

    def _reset_parameters_to_defaults(self):
        """Reset all parameters to their default values."""
        # Reset ephemerides
        self.t0_param.value_input.value = 2458000.0
        self.t0_param.adjust_checkbox.value = False
        self.period_param.value_input.value = 2.5
        self.period_param.adjust_checkbox.value = False

        # Reset primary star
        self.mass1_param.value_input.value = 1.0
        self.mass1_param.adjust_checkbox.value = False
        self.radius1_param.value_input.value = 1.0
        self.radius1_param.adjust_checkbox.value = False
        self.temperature1_param.value_input.value = 5778.0
        self.temperature1_param.adjust_checkbox.value = False

        # Reset secondary star
        self.mass2_param.value_input.value = 0.8
        self.mass2_param.adjust_checkbox.value = False
        self.radius2_param.value_input.value = 0.8
        self.radius2_param.adjust_checkbox.value = False
        self.temperature2_param.value_input.value = 4800.0
        self.temperature2_param.adjust_checkbox.value = False

        # Reset orbit
        self.inclination_param.value_input.value = 90.0
        self.inclination_param.adjust_checkbox.value = False
        self.eccentricity_param.value_input.value = 0.0
        self.eccentricity_param.adjust_checkbox.value = False
        self.omega_param.value_input.value = 0.0
        self.omega_param.adjust_checkbox.value = False

    async def compute_model(self):
        """Compute Phoebe model with current parameters."""
        try:
            # Show button loading indicator
            self.compute_button.props('loading')

            # Run the compute operation asynchronously to avoid blocking the UI
            import asyncio
            response = await asyncio.get_event_loop().run_in_executor(
                None, self.phoebe_api.run_compute
            )

            if response['status'] == 'success':
                model_data = response.get('result', {}).get('model', {})

                for ds_label, ds_meta in self.dataset.datasets.items():
                    ds_meta['model_fluxes'] = model_data[ds_label].get('fluxes', [])
                    ds_meta['model_rv1s'] = model_data[ds_label].get('rv1s', [])
                    ds_meta['model_rv2s'] = model_data[ds_label].get('rv2s', [])
            else:
                ui.notify(f"Model computation failed: {response.get('error', 'Unknown error')}", type='negative')

        except Exception as e:
            ui.notify(f"Error computing model: {str(e)}", type='negative')
        finally:
            # Remove button loading indicator
            self.compute_button.props(remove='loading')

    async def fit_parameters(self):
        """Fit adjustable parameters to data."""
        try:
            # Show button loading indicator
            self.fit_button.props('loading')

            adjustable_params = []

            # Check all parameters for adjustment
            if self.t0_param.adjust_checkbox.value:
                adjustable_params.append('t0_supconj@binary')
            if self.period_param.adjust_checkbox.value:
                adjustable_params.append('period@binary')
            if self.mass1_param.adjust_checkbox.value:
                adjustable_params.append('mass@primary')
            if self.radius1_param.adjust_checkbox.value:
                adjustable_params.append('requiv@primary')
            if self.temperature1_param.adjust_checkbox.value:
                adjustable_params.append('teff@primary')
            if self.mass2_param.adjust_checkbox.value:
                adjustable_params.append('mass@secondary')
            if self.radius2_param.adjust_checkbox.value:
                adjustable_params.append('requiv@secondary')
            if self.temperature2_param.adjust_checkbox.value:
                adjustable_params.append('teff@secondary')
            if self.inclination_param.adjust_checkbox.value:
                adjustable_params.append('incl@binary')
            if self.eccentricity_param.adjust_checkbox.value:
                adjustable_params.append('ecc@binary')
            if self.omega_param.adjust_checkbox.value:
                adjustable_params.append('per0@binary')

            if not adjustable_params:
                ui.notify('No parameters marked for adjustment', type='warning')
                return

            if not self.client_id or not self.phoebe_api:
                ui.notify('Session not available for parameter fitting', type='error')
                return

            ui.notify(f'Fitting parameters: {", ".join(adjustable_params)}', type='info')

            # TODO: Use self.phoebe_api.send_command() to fit parameters
            # For now, just show completion
            ui.notify('Parameter fitting completed', type='positive')

        except Exception as e:
            ui.notify(f"Error fitting parameters: {str(e)}", type='negative')
        finally:
            # Remove button loading indicator
            self.fit_button.props(remove='loading')

    def get_user_info(self):
        """Get user information for logging or display purposes."""
        if self.user_first_name and self.user_last_name:
            return f"{self.user_first_name} {self.user_last_name}"
        return "Unknown User"

    def get_session_info(self):
        """Get session information for logging or display purposes."""
        return {
            'client_id': self.client_id,
            'user_name': self.get_user_info(),
            'session_active': bool(self.client_id)
        }


if __name__ in {"__main__", "__mp_main__"}:
    # Initialize API clients
    session_api = SessionAPI(base_url="http://localhost:8001")
    phoebe_api = PhoebeAPI(base_url="http://localhost:8001")

    # Create UI with API instances - this will automatically start one session
    app = PhoebeUI(session_api=session_api, phoebe_api=phoebe_api)

    ui.run(host='0.0.0.0', port=8082, title='Phoebe UI', reload=False)
