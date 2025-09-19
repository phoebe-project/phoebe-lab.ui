from nicegui import ui
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from client.session_api import SessionAPI
from client.phoebe_api import PhoebeAPI
from ui.utils import time_to_phase, alias_data, flux_to_magnitude
from asyncio import get_event_loop


class PhoebeParameterWidget:
    """
    Parent class for all parameter widgets.
    """

    def __init__(self, twig: str, label: str, format: str = '%.3f', api=None, ui_hook=None, visible=True, sensitive=True, **kwargs):
        self.api = api  # Reference to API for setting values
        self.ui_hook = ui_hook  # Optional hook for UI updates

        # grab parameter information from the api:
        request = api.get_parameter(twig)
        if request['success']:
            par = request['result']
            value = par['value']
            self.uniqueid = par['uniqueid']
            self.twig = par['twig']  # fully qualified twig
        else:
            raise ValueError(f"Failed to retrieve parameter {twig}: {request.get('error', 'Unknown error')}")

        if par['Class'] in ['FloatParameter', 'IntParameter']:
            order_of_mag = np.floor(np.log10(np.abs(value))) if value != 0 else 0
            limits = par['limits']
            self.widget = ui.number(
                label=label,
                value=value,
                format=format,
                min=limits[0],
                max=limits[1],
                step=float(10**(order_of_mag-2))
            ).classes('flex-1 min-w-0')

        elif par['Class'] == 'ChoiceParameter':
            self.widget = ui.select(
                label=label,
                options=par['choices'],
                value=value
            ).classes('flex-1 min-w-0')

        elif par['Class'] == 'BoolParameter':
            self.widget = ui.checkbox(
                text=label,
                value=value
            ).classes('flex-1 min-w-0')

        else:
            raise NotImplementedError(f"Parameter class {par['Class']} not supported yet.")

        # set default visibility and sensitivity:
        self.visible = visible
        self.sensitive = sensitive

        # if parameter is constrained, disable the widget
        response = api.is_parameter_constrained(uniqueid=self.uniqueid)
        if response['success']:
            self.set_sensitive(not response['result'])

        self.widget.on('update:model-value', self.on_value_changed)

    def set_sensitive(self, sensitive: bool):
        if sensitive:
            self.widget.enable()
            self.sensitive = True
        else:
            self.widget.disable()
            self.sensitive = False

    def set_visible(self, visible: bool):
        self.widget.classes(remove='hidden') if visible else self.widget.classes(add='hidden')
        self.visible = visible

    def update_uniqueid(self):
        response = self.api.get_uniqueid(twig=self.twig)
        if response['success']:
            self.uniqueid = response['result']
        else:
            self.uniqueid = None

    def get_value(self):
        if self.widget:
            return self.widget.value

    def set_value(self, value):
        if self.widget:
            self.widget.value = value

    def on_value_changed(self, event):
        if event is None:
            return

        value = self.widget.value

        try:
            response = self.api.set_value(uniqueid=self.uniqueid, value=value)
            if not response.get('success', False):
                ui.notify(f'Failed to set {self.twig}: {response.get("error", "Unknown error")}', type='negative')
        except Exception as e:
            ui.notify(f'Error setting {self.twig}: {str(e)}', type='negative')

        if self.ui_hook:
            self.ui_hook(value)


class PhoebeAdjustableParameterWidget:
    """
    Widget for a single Phoebe parameter with value, adjustment checkbox, and step size.
    """

    def __init__(self, twig: str, label: str, step: float = 0.001, vformat: str = '%.3f',
                 sformat: str = '%.3f', adjust: bool = False, api=None, ui_ref=None, ui_hook=None, **kwargs):
        self.step = step
        self.adjust = adjust
        self.ui = ui_ref

        with ui.row().classes('items-center gap-2 w-full') as self.container:
            # Parameter label
            ui.label(f'{label}:').classes('w-24 flex-shrink-0 text-sm')

            # Value input
            self.value_input = PhoebeParameterWidget(
                twig=twig,
                label='Value',
                format=vformat,
                api=api,
                ui_hook=ui_hook,
                **kwargs
            )

            # Checkbox for adjustment
            self.adjust_checkbox = ui.checkbox(text='Adjust', value=adjust).classes('flex-shrink-0')
            self.adjust_checkbox.on('update:model-value', self.on_adjust_toggled)

            # Step size input (after checkbox)
            self.step_input = ui.number(
                label='Step',
                value=step,
                format=sformat,
                step=step/10
            ).classes('flex-1 min-w-0')

            # Set initial state of step input
            self.on_adjust_toggled()

        # Set twig and uniqueid to that of the value input:
        self.twig = self.value_input.twig
        self.uniqueid = self.value_input.uniqueid

        # Set initial visibility and sensitivity:
        self.visible = True
        self.sensitive = True

    def set_visible(self, visible: bool):
        self.container.classes(remove='hidden') if visible else self.container.classes(add='hidden')
        self.visible = visible

    def set_sensitive(self, sensitive: bool):
        self.value_input.set_sensitive(sensitive)
        self.sensitive = self.value_input.sensitive

    def update_uniqueid(self):
        self.value_input.update_uniqueid()
        self.uniqueid = self.value_input.uniqueid

    def get_twig(self):
        return self.value_input.twig

    def get_value(self):
        return self.value_input.widget.value

    def set_value(self, value):
        self.value_input.set_value(value)

    def on_value_changed(self, event=None):
        return self.value_input.on_value_changed(event)

    def on_adjust_toggled(self):
        """Handle adjust checkbox state change."""
        self.adjust = self.adjust_checkbox.value

        if self.adjust:
            self.step_input.enable()
            self.step_input.classes(remove='text-gray-400')
            if self.ui.fully_initialized:
                self.ui.add_parameter_to_solver_table(self)
        else:
            self.step_input.disable()
            self.step_input.classes(add='text-gray-400')
            if self.ui.fully_initialized:
                self.ui.remove_parameter_from_solver_table(self)


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
            self.api.set_value(twig=f'pblum_mode@{dataset}', value='dataset-scaled')

    def remove(self, dataset):
        if dataset not in self.datasets:
            raise ValueError(f'Dataset {dataset} does not exist.')

        self.api.remove_dataset(dataset)
        del self.datasets[dataset]

    def readd_all(self):
        for dataset in self.datasets.values():
            compute_phases = np.linspace(
                dataset['phase_min'],
                dataset['phase_max'],
                dataset['n_points']
            )

            params = {
                'dataset': dataset.get('dataset'),
                'passband': dataset.get('passband'),
                'compute_phases': compute_phases,
                'times': dataset.get('times'),
                'sigmas': dataset.get('sigmas')
            }

            if dataset['kind'] == 'lc':
                params['fluxes'] = dataset.get('fluxes', [])
            if dataset['kind'] == 'rv':
                params['rv1s'] = dataset.get('rv1s', [])
                params['rv2s'] = dataset.get('rv2s', [])

            self.api.add_dataset(**params)
            if len(dataset['fluxes']) > 0 or len(dataset['rv1s']) > 0 or len(dataset['rv2s']) > 0:
                self.api.set_value(twig=f'pblum_mode@{dataset["dataset"]}', value='dataset-scaled')


class PhoebeUI:
    """Main Phoebe UI."""

    def __init__(self, session_api: SessionAPI = None, phoebe_api: PhoebeAPI = None):
        # there are many callbacks that depend on the UI being fully
        # initialized, so we keep the UI state explicitly:
        self.fully_initialized = False

        self.session_api = session_api
        self.phoebe_api = phoebe_api
        self.client_id = None  # Will be set when session is established
        self.user_first_name = None
        self.user_last_name = None

        # Parameters:
        self.parameters = {}

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

        self.fully_initialized = True

    def add_parameter(self, twig: str, label: str, step: float, adjust: bool, vformat: str = '%.3f', sformat: str = '%.3f', on_value_changed=None):
        parameter = PhoebeAdjustableParameterWidget(
            twig=twig,
            label=label,
            step=step,
            adjust=adjust,
            vformat=vformat,
            sformat=sformat,
            api=self.phoebe_api,
            ui_ref=self,
            ui_hook=on_value_changed,
        )

        # name the parameter by its fully qualified twig:
        self.parameters[parameter.twig] = parameter

    def create_parameter_panel(self):
        # Model selection
        self.model_select = ui.select(
            options={
                'phoebe': 'PHOEBE',
            },
            value='phoebe',
            label='Model'
        ).classes('w-full mb-4')

        self.morphology_select = ui.select(
            options={
                'detached': 'Detached binary',
                'semi-detached': 'Semi-detached binary',
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
            self.add_parameter(
                twig='t0_supconj@binary',
                label='T₀ (BJD)',
                step=0.01,
                adjust=False,
                vformat='%.8f',
                sformat='%.3f',
                on_value_changed=self.on_ephemeris_changed
            )

            self.add_parameter(
                twig='period@binary',
                label='Period (d)',
                step=0.0001,
                adjust=False,
                vformat='%.8f',
                sformat='%.3f',
                on_value_changed=self.on_ephemeris_changed
            )

        # Primary star parameters
        with ui.expansion('Primary Star', icon='wb_sunny', value=False).classes('w-full mb-4'):
            self.add_parameter(
                twig='mass@primary@component',
                label='Mass (M₀)',
                step=0.01,
                adjust=False,
            )

            self.add_parameter(
                twig='requiv@primary@component',
                label='Radius (R₀)',
                step=0.01,
                adjust=False,
            )

            self.add_parameter(
                twig='teff@primary@component',
                label='Temperature (K)',
                vformat='%d',
                step=10.0,
                adjust=False,
            )

        # Secondary star parameters
        with ui.expansion('Secondary Star', icon='wb_sunny', value=False).classes('w-full mb-4'):
            self.add_parameter(
                twig='mass@secondary@component',
                label='Mass (M₀)',
                step=0.01,
                adjust=False,
            )

            self.add_parameter(
                twig='requiv@secondary@component',
                label='Radius (R₀)',
                step=0.01,
                adjust=False,
            )

            self.add_parameter(
                twig='teff@secondary@component',
                label='Temperature (K)',
                vformat='%d',
                step=10.0,
                adjust=False,
            )

        # Orbit parameters
        with ui.expansion('Orbit', icon='trip_origin', value=False).classes('w-full mb-4'):
            self.add_parameter(
                twig='incl@binary@component',
                label='Inclination (°)',
                step=0.1,
                adjust=False,
            )

            self.add_parameter(
                twig='ecc@binary@component',
                label='Eccentricity',
                step=0.01,
                adjust=False,
            )

            self.add_parameter(
                twig='per0@binary@component',
                label='Argument of periastron (°)',
                step=1.0,
                adjust=False,
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
                'overlayNoRowsTemplate': 'No datasets added. Click "Add" to define a synthetic dataset or load observations.',
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
                # Primary star parameters row
                with ui.row().classes('gap-4 items-center w-full mb-3') as self.compute_row_primary:
                    ui.label('Primary star:').classes('w-32 flex-shrink-0 text-sm font-medium')
                    self.parameters['atm@primary'] = PhoebeParameterWidget(
                        twig='atm@primary',
                        label='Model atmosphere',
                        api=self.phoebe_api
                    )

                    self.parameters['ntriangles@primary'] = PhoebeParameterWidget(
                        twig='ntriangles@primary',
                        label='Surface elements',
                        format='%d',
                        api=self.phoebe_api
                    )

                    self.parameters['distortion_method@primary'] = PhoebeParameterWidget(
                        twig='distortion_method@primary',
                        label='Distortion',
                        api=self.phoebe_api
                    )

                # Secondary star parameters row
                with ui.row().classes('gap-4 items-center w-full mb-3') as self.compute_row_secondary:
                    ui.label('Secondary star:').classes('w-32 flex-shrink-0 text-sm font-medium')
                    self.parameters['atm@secondary'] = PhoebeParameterWidget(
                        twig='atm@secondary',
                        label='Model atmosphere',
                        api=self.phoebe_api
                    )

                    self.parameters['ntriangles@secondary'] = PhoebeParameterWidget(
                        twig='ntriangles@secondary',
                        label='Surface elements',
                        format='%d',
                        api=self.phoebe_api
                    )

                    self.parameters['distortion_method@secondary'] = PhoebeParameterWidget(
                        twig='distortion_method@secondary',
                        label='Distortion',
                        api=self.phoebe_api
                    )

                # with ui.row().classes('gap-4 items-center w-full mb-3') as self.compute_row_envelope:
                #     ui.label('Envelope:').classes('w-32 flex-shrink-0 text-sm font-medium')

                #     self.parameters['ntriangles@envelope'] = PhoebeParameterWidget(
                #         twig='ntriangles@envelope',
                #         label='Surface elements',
                #         format='%d',
                #         api=self.phoebe_api
                #     )

                # System parameters and compute button row
                with ui.row().classes('gap-4 items-center w-full'):
                    self.parameters['irrad_method'] = PhoebeParameterWidget(
                        twig='irrad_method',
                        label='Irradiation method',
                        api=self.phoebe_api
                    )

                    self.parameters['dynamics_method'] = PhoebeParameterWidget(
                        twig='dynamics_method',
                        label='Dynamics method',
                        api=self.phoebe_api
                    )

                    self.parameters['boosting_method'] = PhoebeParameterWidget(
                        twig='boosting_method',
                        label='Boosting method',
                        api=self.phoebe_api
                    )

                    self.parameters['ltte'] = PhoebeParameterWidget(
                        twig='ltte',
                        label='Include LTTE',
                        api=self.phoebe_api
                    )
                    
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

            with ui.column().classes('h-full p-4 min-w-0 w-full'):
                with ui.row().classes('gap-4 items-center w-full'):

                    # Solver selection
                    self.solver_select = ui.select(
                        options={'dc': 'Differential corrections'},
                        value='dc',
                        label='Solver'
                    ).classes('flex-1')

                    self.parameters['deriv_method@solver'] = PhoebeParameterWidget(
                        twig='deriv_method@solver',
                        label='Derivatives',
                        options=['symmetric', 'asymmetric'],
                        api=self.phoebe_api
                    )

                    self.parameters['expose_lnprobabilities@solver'] = PhoebeParameterWidget(
                        twig='expose_lnprobabilities@solver',
                        label='Expose ln-probabilities',
                        api=self.phoebe_api
                    )

                    self.fit_button = ui.button(
                        'Run solver',
                        on_click=self.run_solver,
                        icon='tune'
                    ).classes('h-12 flex-2')

                # Initialize empty table
                self.solution_table = ui.table(
                    columns=[
                        {'name': 'parameter', 'label': 'Adjusted Parameter', 'field': 'parameter', 'align': 'left'},
                        {'name': 'initial', 'label': 'Initial Value', 'field': 'initial', 'align': 'right'},
                        {'name': 'fitted', 'label': 'New Value', 'field': 'fitted', 'align': 'right'},
                        {'name': 'change_percent', 'label': 'Percent Change', 'field': 'change_percent', 'align': 'right'},
                    ],
                    rows=[],
                    row_key='parameter',
                ).classes('w-full').props('no-data-label="No parameters selected for adjustment."')

                # Adopt solution button (right-justified)
                with ui.row().classes('w-full justify-end mt-3'):
                    self.adopt_solution_button = ui.button(
                        'Adopt Solution',
                        icon='check_circle',
                        on_click=self.adopt_solver_solution
                    ).classes('bg-green-600 text-white px-6 py-2')

                    # disable it by default (no solution yet)
                    self.adopt_solution_button.props('disabled')

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

        period = self.parameters['period@binary@orbit@component'].get_value()
        t0 = self.parameters['t0_supconj@binary@orbit@component'].get_value()

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
                    if not ds_meta['model_fluxes']:
                        ui.notify(f'No model fluxes available for dataset {ds_label}. Please compute the model first.', type='warning')
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
            ui.label('Welcome to Phoebe Lab UI').classes('text-xl font-bold mb-4')

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
                              f'to "{new_morphology}" will affect the constraints between parameters.')
            ui.label(morphology_msg)
            ui.label('Do you want to continue?').classes('mb-4')

            with ui.row().classes('gap-4 justify-end w-full'):
                ui.button('Cancel', on_click=lambda: self._cancel_morphology_change(dialog)).classes('bg-gray-500')
                self.morph_confirm_btn = ui.button(
                    'Continue',
                    on_click=lambda: self._confirm_morphology_change(dialog, new_morphology)
                )
                self.morph_confirm_btn.classes('bg-red-500')

        dialog.open()

    def _cancel_morphology_change(self, dialog):
        """Cancel morphology change and revert selection."""
        dialog.close()
        # Revert to previous morphology without triggering callback
        self.morphology_select.value = self._current_morphology
        ui.notify('Morphology change cancelled', type='info')

    def update_morphology(self, new_morphology):
        # change morphology in the backend:
        self.phoebe_api.change_morphology(new_morphology)

        # cycle through all phoebe parameters defined in the UI:
        for param_widget in self.parameters.values():
            # update parameter uniqueids:
            param_widget.update_uniqueid()

            # disable parameters if they're constrained:
            response = self.phoebe_api.is_parameter_constrained(uniqueid=param_widget.uniqueid)
            if response['success']:
                constrained = response['result']
                param_widget.set_visible(not constrained)
            else:
                ui.notify(f"Failed to check if parameter {param_widget.twig} is constrained", type='negative')

            # update the value:
            if not constrained:
                param_widget.on_value_changed(event=False)

        # Readd all datasets:
        self.dataset.readd_all()

    async def _confirm_morphology_change(self, dialog, new_morphology):
        self.morph_confirm_btn.props('loading')

        try:
            await get_event_loop().run_in_executor(
                None, self.update_morphology, new_morphology
            )
        finally:
            self.morph_confirm_btn.props(remove='loading')

        dialog.close()

        ui.notify(f'Morphology changed to {new_morphology}.', type='positive')

    async def compute_model(self):
        """Compute Phoebe model with current parameters."""
        try:
            # Show button loading indicator
            self.compute_button.props('loading')

            # Run the compute operation asynchronously to avoid blocking the UI
            response = await get_event_loop().run_in_executor(
                None, self.phoebe_api.run_compute
            )

            if response.get('success', False):
                model_data = response.get('result', {}).get('model', {})

                for ds_label, ds_meta in self.dataset.datasets.items():
                    if ds_label in model_data:
                        ds_data = model_data[ds_label]
                        ds_meta['model_fluxes'] = ds_data.get('fluxes', [])
                        ds_meta['model_rv1s'] = ds_data.get('rv1s', [])
                        ds_meta['model_rv2s'] = ds_data.get('rv2s', [])
                    else:
                        ds_meta['model_fluxes'] = []
                        ds_meta['model_rv1s'] = []
                        ds_meta['model_rv2s'] = []
                
                ui.notify('Model computed successfully!', type='positive')
            else:
                ui.notify(f"Model computation failed: {response.get('error', 'Unknown error')}", type='negative')

        except Exception as e:
            ui.notify(f"Error computing model: {str(e)}", type='negative')
        finally:
            # Remove button loading indicator
            self.compute_button.props(remove='loading')

    async def run_solver(self):
        fit_parameters = [twig for twig, parameter in self.parameters.items() if hasattr(parameter, 'adjust') and parameter.adjust]
        if not fit_parameters:
            ui.notify('No parameters selected for fitting', type='warning')
            return

        steps = [self.parameters[twig].step for twig in fit_parameters]

        self.phoebe_api.set_value(twig='fit_parameters@solver', value=fit_parameters)
        self.phoebe_api.set_value(twig='steps@solver', value=steps)

        try:
            # Show button loading indicator
            self.fit_button.props('loading')

            # Run the compute operation asynchronously to avoid blocking the UI
            response = await get_event_loop().run_in_executor(
                None, self.phoebe_api.run_solver
            )

            if response.get('success', False):
                solution_data = response.get('result', {}).get('solution', {})

                # Update the solver results table
                self.update_solution_table(solution_data)

                # Enable adopt solution button:
                self.adopt_solution_button.props(remove='disabled')

                ui.notify("Model fitting succeeded", type='positive')
            else:
                ui.notify(f"Model fitting failed: {response.get('error', 'Unknown error')}", type='negative')

        except Exception as e:
            ui.notify(f"Error fitting parameters: {str(e)}", type='negative')
        finally:
            # Remove button loading indicator
            self.fit_button.props(remove='loading')

    def update_solution_table(self, solution_data):
        """Update the solver results table with the fitting results."""

        # Extract solution data
        fit_parameters = solution_data.get('fit_parameters')
        initial_values = solution_data.get('initial_values')
        fitted_values = solution_data.get('fitted_values')

        # Prepare table data
        table_data = []
        for i, param in enumerate(fit_parameters):
            initial_val = initial_values[i]
            fitted_val = fitted_values[i]

            # Calculate percentage change
            if initial_val != 0:
                percent_change = ((fitted_val - initial_val) / initial_val) * 100
                percent_change_str = f'{percent_change:+.2f}%'
            else:
                percent_change_str = 'N/A'

            table_data.append({
                'parameter': param,
                'initial': f'{initial_val:.6f}',
                'fitted': f'{fitted_val:.6f}',
                'change_percent': percent_change_str
            })

        # Update the table
        self.solution_table.rows = table_data
        self.solution_table.update()

    def add_parameter_to_solver_table(self, par):
        rows = list(self.solution_table.rows)
        twig = par.get_twig()

        # only add a parameter if it's not already in the table:
        if not any(row['parameter'] == twig for row in rows):
            row_data = {
                'parameter': twig,
                'initial': par.get_value(),
                'fitted': 'n/a',
                'change_percent': 'n/a'
            }

            rows.append(row_data)
            self.solution_table.rows = rows
            self.solution_table.update()

    def remove_parameter_from_solver_table(self, par):
        twig = par.get_twig()
        rows = [row for row in self.solution_table.rows if row['parameter'] != twig]
        self.solution_table.rows = rows
        self.solution_table.update()

    def update_parameters_in_solver_table(self):
        rows = list(self.solution_table.rows)

        for i, row in enumerate(rows):
            par = self.parameters[row['parameter']]
            rows[i]['initial'] = par.get_value()
            rows[i]['fitted'] = 'n/a'
            rows[i]['change_percent'] = 'n/a'

        self.solution_table.rows = rows
        self.solution_table.update()

    def adopt_solver_solution(self):
        """Adopt the solver solution by setting fitted values to current parameters."""
        try:
            # Get all rows from the solution table
            for row in self.solution_table.rows:
                twig = row['parameter']
                fitted_value = row.get('fitted', 'n/a')

                # Skip if no fitted value available
                if fitted_value == 'n/a' or fitted_value is None:
                    continue

                # Set the parameter value
                param_widget = self.parameters[twig]
                param_widget.set_value(fitted_value)
                param_widget.on_value_changed(event=False)

            # Update the solution table to reflect the adopted values
            self.update_parameters_in_solver_table()

            # Clear model data since parameters have changed
            for ds_label, ds_meta in self.dataset.datasets.items():
                ds_meta['model_fluxes'] = []
                ds_meta['model_rv1s'] = []
                ds_meta['model_rv2s'] = []

            # Disable adopt solution button:
            self.adopt_solution_button.props('disabled')
        except Exception as e:
            ui.notify(f'Error adopting solver solution: {str(e)}', type='negative')

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

    ui.run(host='0.0.0.0', port=8082, title='PHOEBE Lab UI', reload=False)
