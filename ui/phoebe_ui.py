from nicegui import ui
import numpy as np
import plotly.graph_objects as go
from typing import Optional, Dict
from client.session_api import SessionAPI
from client.phoebe_api import PhoebeAPI


class PhoebeParameterWidget:
    """Widget for a single Phoebe parameter with value, adjustment checkbox, and step size."""
    
    def __init__(self, name: str, label: str, value: float, step: float = 0.001, adjust: bool = False):
        self.name = name
        self.label = label
        self.value = value
        self.step = step
        self.adjust = adjust
        
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


class DataTable:
    """Widget for displaying and managing observational data."""
    
    def __init__(self):
        self.data: Optional[Dict[str, np.ndarray]] = None
        
        with ui.column().classes('w-full'):
            with ui.row().classes('gap-2 items-end w-full'):
                self.label_input = ui.input(
                    label='Data Label',
                    value='lc01'
                ).classes('flex-1')
                self.passband_select = ui.select(
                    options=['GoChile:R', 'GoChile:G', 'GoChile:B', 'GoChile:L'],
                    value='GoChile:R',
                    label='Passband'
                ).classes('flex-1')
                ui.button('Load Data', on_click=self.load_sample_data, icon='upload').classes('h-12')
            
            # Data table (will be populated when data is loaded)
            self.table = ui.table(
                columns=[
                    {'name': 'time', 'label': 'Time (BJD)', 'field': 'time'},
                    {'name': 'flux', 'label': 'Flux', 'field': 'flux'},
                    {'name': 'error', 'label': 'Error', 'field': 'error'},
                ],
                rows=[],
                row_key='time'
            ).classes('w-full max-h-60')
    
    def load_sample_data(self):
        """Load sample light curve data."""
        # Generate sample eclipsing binary light curve
        time = np.linspace(0, 10, 200)
        period = 2.5
        phase = (time % period) / period
        
        # Simple eclipse model
        flux = np.ones_like(time)
        primary_eclipse = np.abs(phase - 0.0) < 0.05
        secondary_eclipse = np.abs(phase - 0.5) < 0.03
        
        flux[primary_eclipse] = 0.7  # Primary eclipse (deeper)
        flux[secondary_eclipse] = 0.9  # Secondary eclipse (shallower)
        
        # Add some noise
        error = np.full_like(time, 0.02)
        flux += np.random.normal(0, error)
        
        self.data = {
            'time': time,
            'flux': flux,
            'error': error
        }
        
        # Convert to list of dicts for the table (show only first 20 rows)
        rows = []
        display_count = min(20, len(time))
        for i in range(display_count):
            rows.append({
                'time': float(time[i]),
                'flux': float(flux[i]),
                'error': float(error[i])
            })
        
        # Update table
        self.table.rows = rows
        self.table.update()
        
        total_points = len(self.data["time"])
        if total_points > display_count:
            ui.notify(f'Loaded {total_points} data points (showing first {display_count} rows)', type='positive')
        else:
            ui.notify(f'Loaded {total_points} data points', type='positive')


class LightCurvePlot:
    """Widget for plotting light curves."""
    
    def __init__(self, data_table: DataTable, ui_ref=None):
        self.data_table = data_table
        self.ui_ref = ui_ref  # Reference to main UI for accessing parameters
        self.model_data = None  # Store computed model data
        
        with ui.column().classes('w-full h-full p-4 min-w-0'):
            ui.label('Light Curve Plot').classes('text-lg font-bold')
            
            # Plot controls row
            with ui.row().classes('gap-4 mb-4'):
                # Visibility checkboxes
                self.show_data_checkbox = ui.checkbox(text='Show Data', value=False)
                self.show_data_checkbox.on('update:model-value', lambda: self.update_plot())
                
                self.show_model_checkbox = ui.checkbox(text='Show Model', value=False)
                self.show_model_checkbox.on('update:model-value', lambda: self.update_plot())
                
                # X-axis dropdown
                self.x_axis_select = ui.select(
                    options={'time': 'Time', 'phase': 'Phase'},
                    value='time',
                    label='X-axis'
                ).classes('w-24')
                self.x_axis_select.on('update:model-value', lambda: self.update_plot())
                
                # Y-axis dropdown
                self.y_axis_select = ui.select(
                    options={'magnitude': 'Magnitude', 'flux': 'Flux'},
                    value='magnitude',
                    label='Y-axis'
                ).classes('w-24')
                self.y_axis_select.on('update:model-value', lambda: self.update_plot())
            
            # Plot container
            self.plot = ui.plotly(self._create_empty_plot()).classes('w-full  min-w-0')
            
            # Add resize observer to handle container size changes
            self.plot._props['config'] = {
                'responsive': True,
                'displayModeBar': True,
                'displaylogo': False
            }
    
    def _create_empty_plot(self):
        """Create an empty plot with consistent bounding box styling."""
        fig = go.Figure()
        
        # Determine axis settings based on current selections
        x_title = 'Time (BJD)' if self.x_axis_select.value == 'time' else 'Phase'
        y_title = 'Magnitude' if self.y_axis_select.value == 'magnitude' else 'Flux'
        y_reversed = self.y_axis_select.value == 'magnitude'

        fig.update_layout(
            title='Light Curve',
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
                autorange='reversed' if y_reversed else True,
                zeroline=False,
                showgrid=True,
                gridcolor='lightgray',
                gridwidth=1,
                griddash='dot'
            ),
            plot_bgcolor='white',
            showlegend=True
        )
        
        return fig
    
    def update_plot(self):
        """Update plot based on current visibility settings and data."""
        if self.show_model_checkbox.value and self.model_data is None:
            ui.notify('Model has not been computed yet. Use "Compute Model" first.', type='warning')
            self.show_model_checkbox.value = False
            return

        fig = self._create_empty_plot()

        # Add data trace if requested and available
        if self.show_data_checkbox.value and self.data_table.data is not None:
            data = self.data_table.data
            x_data = (data['time'] % 2.5) / 2.5 if self.x_axis_select.value == 'phase' else data['time']
            y_data = -2.5 * np.log10(data['flux']) if self.y_axis_select.value == 'magnitude' else data['flux']
            y_error = 2.5 * data['error'] / (data['flux'] * np.log(10)) if self.y_axis_select.value == 'magnitude' else data['error']

            fig.add_trace(go.Scatter(
                x=x_data,
                y=y_data,
                error_y=dict(type='data', array=y_error, visible=True),
                mode='markers',
                marker=dict(size=4, color='blue'),
                name=self.data_table.label_input.value or 'Data'
            ))

        # Add model trace if requested and available
        if self.show_model_checkbox.value and self.model_data is not None:
            x_model = (self.model_data['time'] % 2.5) / 2.5 if self.x_axis_select.value == 'phase' else self.model_data['time']
            y_model = -2.5 * np.log10(self.model_data['flux']) if self.y_axis_select.value == 'magnitude' else self.model_data['flux']

            fig.add_trace(go.Scatter(
                x=x_model,
                y=y_model,
                mode='lines',
                line=dict(color='red', width=2),
                name='Model'
            ))

        self.plot.figure = fig
        self.plot.update()
    
    def set_model_data(self, model_data):
        """Set model data from external computation."""
        self.model_data = model_data
        # Auto-enable model visibility when new model is computed
        self.show_model_checkbox.value = True
        self.update_plot()


class PhoebeUI:
    """Main Phoebe UI."""
    
    def __init__(self, session_api: SessionAPI = None, phoebe_api: PhoebeAPI = None):
        self.session_api = session_api
        self.phoebe_api = phoebe_api
        self.client_id = None  # Will be set when session is established
        self.user_first_name = None
        self.user_last_name = None

        # Show startup dialog first
        # self.show_startup_dialog()

        # Create main UI (will be shown after dialog)
        with ui.splitter(value=30).classes('w-full h-screen') as self.main_splitter:
            # Left panel - Parameters, data, and controls
            with self.main_splitter.before:
                with ui.scroll_area().classes('w-full h-full p-4'):
                    self.create_parameter_panel()
            
            # Right panel - Plots and results
            with self.main_splitter.after:
                self.create_plot_panel()

            # Allow plot width change on splitter drag
            self.main_splitter.on_value_change(lambda: ui.run_javascript(f'Plotly.Plots.resize(getHtmlElement({self.light_curve_plot.plot.id}))'))

    def create_parameter_panel(self):
        """Create the parameter control panel."""
        
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
        
        with ui.expansion('Observational Data', icon='table_chart', value=False).classes('w-full mb-4'):
            self.data_table = DataTable()
        
        # Ephemerides parameters
        with ui.expansion('Ephemerides', icon='schedule', value=False).classes('w-full mb-4'):
            # Create parameter widgets for t0 and period
            self.t0_param = PhoebeParameterWidget(
                name='t0',
                label='T₀ (BJD)',
                value=2458000.0,
                step=0.1,
                adjust=False
            )
            
            self.period_param = PhoebeParameterWidget(
                name='period',
                label='Period (d)',
                value=2.5,
                step=0.1,
                adjust=False
            )
        
        # Primary star parameters
        with ui.expansion('Primary Star', icon='wb_sunny', value=False).classes('w-full mb-4'):
            self.mass1_param = PhoebeParameterWidget(
                name='mass1',
                label='Mass (M₀)',
                value=1.0,
                step=0.01,
                adjust=False
            )
            
            self.radius1_param = PhoebeParameterWidget(
                name='radius1',
                label='Radius (R₀)',
                value=1.0,
                step=0.01,
                adjust=False
            )
            
            self.temperature1_param = PhoebeParameterWidget(
                name='temperature1',
                label='Temperature (K)',
                value=5778.0,
                step=10.0,
                adjust=False
            )
        
        # Secondary star parameters
        with ui.expansion('Secondary Star', icon='wb_sunny', value=False).classes('w-full mb-4'):
            self.mass2_param = PhoebeParameterWidget(
                name='mass2',
                label='Mass (M₀)',
                value=0.8,
                step=0.01,
                adjust=False
            )
            
            self.radius2_param = PhoebeParameterWidget(
                name='radius2',
                label='Radius (R₀)',
                value=0.8,
                step=0.01,
                adjust=False
            )
            
            self.temperature2_param = PhoebeParameterWidget(
                name='temperature2',
                label='Temperature (K)',
                value=4800.0,
                step=10.0,
                adjust=False
            )
        
        # Orbit parameters
        with ui.expansion('Orbit', icon='trip_origin', value=False).classes('w-full mb-4'):
            self.inclination_param = PhoebeParameterWidget(
                name='inclination',
                label='Inclination (°)',
                value=90.0,
                step=0.1,
                adjust=False
            )
            
            self.eccentricity_param = PhoebeParameterWidget(
                name='eccentricity',
                label='Eccentricity',
                value=0.0,
                step=0.01,
                adjust=False
            )
            
            self.omega_param = PhoebeParameterWidget(
                name='omega',
                label='Argument of periastron (°)',
                value=0.0,
                step=1.0,
                adjust=False
            )
        
        # Compute controls (outside collapsible container)
        ui.separator().classes('my-4')
        
        # Compute controls
        ui.label('Compute Controls').classes('text-lg font-bold mb-2')
        with ui.row().classes('gap-4 items-end w-full'):
            ui.button('Compute Model', on_click=self.compute_model, icon='calculate').classes('h-12 flex-shrink-0')
            self.n_points_input = ui.number(
                label='Number of synthetic phase points',
                value=201,
                min=50,
                max=2000,
                step=1,
                format='%d'
            ).classes('flex-grow min-w-0')  # Use flex-grow instead of flex-1
        
        with ui.row().classes('gap-4 mt-2'):
            ui.button('Fit Parameters', on_click=self.fit_parameters, icon='tune')
    
    def create_plot_panel(self):
        """Create the plotting panel."""
        with ui.column().classes('w-full h-full p-4 min-w-0'):
            # Light curve plot (pass reference to UI for parameter access)
            self.light_curve_plot = LightCurvePlot(self.data_table, self)
    
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
        
        # Close dialog and show main UI
        self.startup_dialog.close()
        self.main_splitter.style('display: flex')
        
        ui.notify(f'Welcome {first_name} {last_name}! Session {self.client_id} ready.', type='positive')
    
    def initialize_session(self):
        """Initialize a new Phoebe session."""
        if not self.session_api:
            ui.notify('Session API not available', type='error')
            return
        
        try:
            # Start a new session
            response = self.session_api.start_session()
            self.client_id = response.get('client_id')
            
            if self.client_id and self.phoebe_api:
                # Set client ID in Phoebe API
                self.phoebe_api.set_client_id(self.client_id)
                self.session_status.text = f'Session: {self.client_id}'
                ui.notify(f'Session initialized: {self.client_id}', type='positive')
            else:
                ui.notify('Failed to get client ID from session', type='error')
                
        except Exception as e:
            ui.notify(f'Failed to initialize session: {str(e)}', type='error')
    
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
    
    def _on_morphology_change(self):
        """Handle morphology selection change with confirmation dialog."""
        new_morphology = self.morphology_select.value
        
        # If it's the same as current, no need to warn
        if new_morphology == self._current_morphology:
            return
        
        # Show confirmation dialog
        with ui.dialog() as dialog, ui.card():
            ui.label('Warning: Morphology Change').classes('text-lg font-bold mb-4')
            ui.label(f'Changing morphology from "{self._current_morphology}" to "{new_morphology}" will reset all system parameters to their default values.')
            ui.label('Do you want to continue?').classes('mb-4')
            
            with ui.row().classes('gap-4 justify-end w-full'):
                ui.button('Cancel', on_click=lambda: self._cancel_morphology_change(dialog)).classes('bg-gray-500')
                ui.button('Continue', on_click=lambda: self._confirm_morphology_change(dialog, new_morphology)).classes('bg-red-500')
        
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
    
    def compute_model(self):
        """Compute Phoebe model with current parameters."""
        t0 = self.t0_param.value_input.value
        period = self.period_param.value_input.value
        n_points = int(self.n_points_input.value)
        
        # TODO: When session is active, use Phoebe API to compute real model
        # For now, generate synthetic model regardless
        
        # Generate sample model light curve with user-specified number of points
        time = np.linspace(0, 10, n_points)
        phase = (time % period) / period
        
        # Simple model based on parameters
        flux = np.ones_like(time)
        
        # Primary eclipse (using inclination and other parameters)
        inclination = self.inclination_param.value_input.value
        eclipse_depth1 = 0.3 * np.sin(np.radians(inclination))  # Depth depends on inclination
        primary_eclipse = np.abs(phase - 0.0) < 0.04
        
        # Secondary eclipse (shallower, based on temperature ratio)
        temp1 = self.temperature1_param.value_input.value
        temp2 = self.temperature2_param.value_input.value
        temp_ratio = temp2 / temp1
        eclipse_depth2 = eclipse_depth1 * temp_ratio * 0.3
        secondary_eclipse = np.abs(phase - 0.5) < 0.03
        
        flux[primary_eclipse] = 1.0 - eclipse_depth1
        flux[secondary_eclipse] = 1.0 - eclipse_depth2
        
        # Store model data
        model_data = {
            'time': time,
            'flux': flux
        }
        
        # Set model data in plot
        self.light_curve_plot.set_model_data(model_data)
        
        ui.notify(f'Model computed with T₀={t0:.4f}, Period={period:.6f}', type='positive')
    
    def fit_parameters(self):
        """Fit adjustable parameters to data."""
        adjustable_params = []
        if self.t0_param.adjust_checkbox.value:
            adjustable_params.append('t0')
        if self.period_param.adjust_checkbox.value:
            adjustable_params.append('period')
        
        if not adjustable_params:
            ui.notify('No parameters marked for adjustment', type='warning')
            return
        
        if not self.client_id or not self.phoebe_api:
            ui.notify('Session not available for parameter fitting', type='error')
            return
        
        ui.notify(f'Fitting parameters: {", ".join(adjustable_params)}', type='info')
        # TODO: Use self.phoebe_api.send_command() to fit parameters
    
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

    # Create UI with API instances
    app = PhoebeUI(session_api=session_api, phoebe_api=phoebe_api)

    ui.run(host='0.0.0.0', port=8082, title='Phoebe UI')
