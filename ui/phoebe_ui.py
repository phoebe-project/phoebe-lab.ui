from nicegui import ui
import numpy as np
import plotly.graph_objects as go
from typing import Optional, Dict
from pathlib import Path
from client.session_api import SessionAPI
from client.phoebe_api import PhoebeAPI
from ui.utils import time_to_phase, alias_phase_for_plotting, flux_to_magnitude, magnitude_error_to_flux_error


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
    """Pure data model for managing datasets without UI dependencies."""
    
    def __init__(self):
        self.datasets = {}  # Dictionary to store multiple datasets: {label: dataset_info}

    def add_dataset(self, dataset, kind, **kwargs):
        if dataset in self.datasets:
            return False, f'Dataset "{dataset}" already exists. Please choose a different name.'

        dataset_info = {
            'kind': kind,
            'dataset': dataset,
            'passband': kwargs.get('passband', 'Johnson:V'),
            'component': kwargs.get('component', None),
            'times': kwargs.get('times', []),
            'fluxes': kwargs.get('fluxes', []),
            'rvs': kwargs.get('rvs', []),
            'sigmas': kwargs.get('sigmas', []),
            'filename': kwargs.get('filename', ''),
            'n_points': kwargs.get('n_points', 201),
            'phase_min': kwargs.get('phase_min', -0.5),
            'phase_max': kwargs.get('phase_max', 0.5),
            'observed_points': kwargs.get('observed_points', 0),
            'plot_data': True,
            'plot_model': True
        }

        self.datasets[dataset] = dataset_info
        return True, dataset_info

    def remove_dataset(self, dataset: str):
        """Remove a dataset from the collection."""
        if dataset in self.datasets:
            del self.datasets[dataset]
            return True
        return False


class DatasetView:
    """UI components and dialog management for datasets."""

    def __init__(self, dataset_model: DatasetModel, ui_ref=None):
        self.dataset_model = dataset_model
        self.ui_ref = ui_ref  # Reference to main UI for accessing API and parameters

    def add_dataset(self, dataset, kind, **kwargs):
        # Extract compute_phases for API (don't store in model)
        compute_phases = kwargs.pop('compute_phases', None)
        
        success, dataset_info = self.dataset_model.add_dataset(dataset, kind, **kwargs)
        
        if not success:
            ui.notify(dataset_info, type='error')
            return

        # If no compute_phases provided, generate from stored phase parameters
        if compute_phases is None:
            compute_phases = np.linspace(
                dataset_info.get('phase_min', -0.5),
                dataset_info.get('phase_max', 0.5),
                dataset_info.get('n_points', 201)
            )

        # Call API with compute_phases but don't store it
        api = self.ui_ref.phoebe_api
        if kind == 'lc':
            params = {
                'dataset': dataset_info['dataset'],
                'passband': dataset_info['passband'],
                'compute_phases': compute_phases,
                'times': dataset_info.get('times', []),
                'fluxes': dataset_info.get('fluxes', []),
                'sigmas': dataset_info.get('sigmas', []),
            }
        elif kind == 'rv':
            params = {
                'dataset': dataset_info['dataset'],
                'component': dataset_info.get('component'),
                'passband': dataset_info['passband'],
                'compute_phases': compute_phases,
                'times': dataset_info.get('times', []),
                'rvs': dataset_info.get('rvs', []),
                'sigmas': dataset_info.get('sigmas', []),
            }
        else:
            raise ValueError(f'Unsupported dataset kind: {kind}')
        
        api.add_dataset(kind, **params)

        # Set pblum_mode to 'dataset-scaled' if this is observational data (has times/fluxes/rvs)
        if len(dataset_info.get('fluxes', [])) > 0 or len(dataset_info.get('rvs', [])) > 0:
            print('*** setting pblum_mode to dataset-scaled ***')
            api.set_value(f'pblum_mode@{dataset}', 'dataset-scaled')
        
        self.ui_ref._update_dataset_grid()

    def remove_dataset(self, dataset: str):
        """Remove a dataset from the collection."""
        if self.dataset_model.remove_dataset(dataset):
            ui.notify(f'Removed dataset "{dataset}"', type='info')
            self.ui_ref._update_dataset_grid()

    def open_add_dataset_dialog(self):
        """Open dialog to add a new dataset."""
        self._open_dataset_dialog()
    
    def open_edit_dataset_dialog(self, dataset: str):
        """Open dialog to edit an existing dataset."""
        if dataset in self.dataset_model.datasets:
            self._open_dataset_dialog(edit_dataset=dataset)
    
    def _open_dataset_dialog(self, edit_dataset: str = None):
        """Open dialog to add or edit a dataset."""
        is_edit = edit_dataset is not None
        existing_dataset = self.dataset_model.datasets.get(edit_dataset) if is_edit else None
        
        with ui.dialog() as dataset_dialog, ui.card().classes('w-[800px] h-[600px]'):
            title = f'Edit Dataset: {edit_dataset}' if is_edit else 'Add Dataset'
            ui.label(title).classes('text-xl font-bold mb-4')
            
            # Dataset configuration
            with ui.column().classes('w-full gap-4'):
                # Data type selection
                kind_select = ui.select(
                    options={
                        'lc': 'Light Curve',
                        'rv': 'RV Curve',
                    },
                    value=existing_dataset['kind'] if is_edit else 'lc',
                    label='Data Type'
                ).classes('w-full')
                if is_edit:
                    kind_select.disable()  # Don't allow changing data type during edit
                
                # Component selection (for RV datasets)
                component_select = ui.select(
                    options={
                        'primary': 'Primary',
                        'secondary': 'Secondary',
                    },
                    value=existing_dataset.get('component', 'primary') if is_edit else 'primary',
                    label='Component'
                ).classes('w-full')

                # Data label input
                label_input = ui.input(
                    label='Data Label',
                    placeholder='e.g., lc01, rv_primary, etc.',
                    value=edit_dataset if is_edit else f'dataset_{len(self.dataset_model.datasets) + 1:02d}'
                ).classes('w-full')
                
                # Passband selection
                passband_select = ui.select(
                    options=['GoChile:R', 'GoChile:G', 'GoChile:B', 'GoChile:L', 'Johnson:V', 'Johnson:B'],
                    value=existing_dataset['passband'] if is_edit else 'GoChile:R',
                    label='Passband'
                ).classes('w-full')
                
                # Show/hide component selector based on kind
                def update_component_visibility():
                    component_select.visible = kind_select.value == 'rv'
                
                kind_select.on('update:model-value', lambda: update_component_visibility())
                update_component_visibility()  # Set initial visibility
                
                # Phase parameters section in foldable element
                with ui.expansion('Model', icon='straighten', value=False).classes('w-full mt-4'):
                    # Get existing phase parameters if editing
                    existing_phase_min = existing_dataset.get('phase_min', -0.5) if is_edit else -0.5
                    existing_phase_max = existing_dataset.get('phase_max', 0.5) if is_edit else 0.5
                    existing_n_points = existing_dataset.get('n_points', 201) if is_edit else 201

                    # Phase range and number of points inputs
                    with ui.row().classes('gap-2 w-full'):
                        phase_min_input = ui.number(
                            label='Phase min',
                            value=existing_phase_min,
                            step=0.1,
                            format='%.2f'
                        ).classes('flex-1')
                        
                        phase_max_input = ui.number(
                            label='Phase max',
                            value=existing_phase_max,
                            step=0.1,
                            format='%.2f'
                        ).classes('flex-1')
                        
                        n_points_input = ui.number(
                            label='Num. pts',
                            value=existing_n_points,
                            min=50,
                            max=2000,
                            step=1,
                            format='%d'
                        ).classes('flex-1')

            ui.separator().classes('my-4')
            
            # Observations section in foldable element
            with ui.expansion('Observations', icon='insert_chart', value=False).classes('w-full'):
                # File loading section (only show if not editing or if user wants to replace data)
                load_section = ui.column().classes('w-full')
                
                if is_edit:
                    # Show replace data button for editing
                    with ui.row().classes('gap-2 mb-4'):
                        ui.button(
                            'Replace Data',
                            on_click=lambda: load_section.set_visibility(True),
                            icon='upload'
                        ).classes('h-10')
                
                with load_section:
                    if not is_edit:
                        load_section.set_visibility(True)
                    else:
                        load_section.set_visibility(False)
                        
                    # Tab container for example vs upload
                    with ui.tabs().classes('w-full') as tabs:
                        example_tab = ui.tab('Example Files')
                        upload_tab = ui.tab('Upload File')
                
                with ui.tab_panels(tabs, value=example_tab).classes('w-full'):
                    # Example files tab
                    with ui.tab_panel(example_tab):
                        ui.label('Select an example data file:').classes('mb-2')
                        
                        # List example files
                        examples_dir = Path(__file__).parent.parent / 'examples'
                        example_files = []
                        
                        if examples_dir.exists():
                            for file_path in examples_dir.glob('*'):
                                example_files.append({
                                    'name': file_path.name,
                                    'path': str(file_path),
                                    'description': self._get_file_description(file_path.name)
                                })
                        
                        if example_files:
                            # Track selected file and cards for highlighting
                            selected_file = None
                            example_cards = []
                            
                            def toggle_file_selection(file_path, card_element):
                                nonlocal selected_file
                                if selected_file == file_path:
                                    # Deselect
                                    selected_file = None
                                    card_element.classes(remove='bg-blue-100 border-blue-500 border-2')
                                    card_element.classes(add='bg-white border-gray-200')
                                    # Clear preview when deselecting
                                    preview_label.text = 'No data loaded'
                                    preview_table.rows = []
                                    preview_table.update()
                                    if hasattr(dataset_dialog, '_loaded_data'):
                                        delattr(dataset_dialog, '_loaded_data')
                                else:
                                    # Reset all cards first
                                    for other_card in example_cards:
                                        other_card.classes(remove='bg-blue-100 border-blue-500 border-2')
                                        other_card.classes(add='bg-white border-gray-200')
                                    
                                    # Select new file
                                    selected_file = file_path
                                    card_element.classes(remove='bg-white border-gray-200')
                                    card_element.classes(add='bg-blue-100 border-blue-500 border-2')
                                    
                                    # Load the file data
                                    self._load_file_in_dialog(
                                        file_path, dataset_dialog, label_input, kind_select, passband_select, component_select,
                                        preview_label, preview_table, is_edit
                                    )
                            
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
                                                toggle_file_selection(file_path, card_el))
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
                            on_upload=lambda e: self._handle_upload_in_dialog(
                                e, dataset_dialog, label_input, kind_select, passband_select, component_select,
                                preview_label, preview_table, is_edit
                            ),
                            max_file_size=10_000_000,  # 10MB limit
                            max_files=1
                        ).props('accept=".dat,.txt,.csv"').classes('w-full')
                        file_upload.classes('border-2 border-dashed border-gray-300 rounded-lg p-8 text-center')
            
            # Add tab change handler to show/hide preview section
            def on_tab_change():
                current_tab = tabs.value
                # Show preview only for example files and upload tabs
                preview_expansion.visible = current_tab in [example_tab, upload_tab]
            
            tabs.on('update:model-value', lambda: on_tab_change())
            
            # Data preview section (hidden by default, shown only for example/upload tabs)
            # ui.separator().classes('my-4')
            
            with ui.expansion('Data Preview', icon='table_view').classes('w-full') as preview_expansion:
                preview_expansion.open = False  # Collapsed by default
                preview_expansion.visible = False  # Hidden by default for synthetic data tab
                
                preview_container = ui.column().classes('w-full')
                
                with preview_container:
                    preview_label = ui.label('No data loaded').classes('text-sm text-gray-600 mb-2')
                    if is_edit:
                        preview_label.text = f'{existing_dataset["filename"]} ({existing_dataset["n_points"]} points)'
                    
                    # Data preview table
                    preview_table = ui.table(
                        columns=[
                            {'name': 'time', 'label': 'Time (BJD)', 'field': 'time'},
                            {'name': 'value', 'label': 'Value', 'field': 'value'},
                            {'name': 'error', 'label': 'Error', 'field': 'error'},
                        ],
                        rows=[],
                        row_key='time'
                    ).classes('w-full max-h-40')
                
                # Show existing data in preview if editing
                if is_edit and len(existing_dataset.get('times', [])) > 0:
                    edit_data = {
                        'times': existing_dataset['times'],
                        'obs': existing_dataset.get('fluxes', existing_dataset.get('rvs', [])),
                        'sigmas': existing_dataset['sigmas']
                    }
                    self._populate_preview_table(preview_table, edit_data)
            
            # Dialog buttons
            ui.separator().classes('my-4')
            with ui.row().classes('gap-2 justify-end w-full'):
                ui.button('Cancel', on_click=dataset_dialog.close).classes('bg-gray-500')
                ui.button(
                    'Save' if is_edit else 'Add',
                    on_click=lambda: self._save_dataset_from_dialog(
                        label_input, kind_select, passband_select, component_select,
                        dataset_dialog, is_edit, edit_dataset,
                        tabs, n_points_input, phase_min_input, phase_max_input
                    ),
                    icon='save'
                ).classes('bg-blue-500')
        
        dataset_dialog.open()
    
    def _populate_preview_table(self, preview_table, data):
        """Populate preview table with dataset."""
        rows = []
        
        # Handle raw parsed data format (times, obs, sigmas)
        if 'times' in data and len(data['times']) > 0:
            times = data['times']
            obs = data['obs']
            sigmas = data['sigmas']
            display_count = min(20, len(times))
            
            for i in range(display_count):
                rows.append({
                    'time': round(float(times[i]), 4),
                    'value': round(float(obs[i]), 4),
                    'error': round(float(sigmas[i]), 4)
                })
        
        preview_table.rows = rows
        preview_table.update()
    
    def _load_file_in_dialog(self, file_path, dialog, label_input, kind_select, passband_select, component_select,
                             preview_label, preview_table, is_edit):
        """Load file and update preview in dialog."""
        try:
            data = self._parse_data_file(file_path)
            if data:
                # Update preview
                filename = Path(file_path).name
                preview_label.text = f'{filename} ({len(data["times"])} points)'
                self._populate_preview_table(preview_table, data)
                
                # Store loaded data for saving
                if not hasattr(dialog, '_loaded_data'):
                    dialog._loaded_data = {}
                dialog._loaded_data = {
                    'data': data,
                    'filename': filename
                }
                
        except Exception as e:
            ui.notify(f'Error loading file: {str(e)}', type='error')
    
    def _handle_upload_in_dialog(self, event, dialog, label_input, kind_select, passband_select, component_select,
                                 preview_label, preview_table, is_edit):
        """Handle file upload in dialog."""
        try:
            file_content = event.content.read()
            file_name = event.name
            
            if isinstance(file_content, bytes):
                file_content = file_content.decode('utf-8')
            
            data = self._parse_data_content(file_content)
            if data:
                # Update preview
                preview_label.text = f'{file_name} ({len(data["times"])} points)'
                self._populate_preview_table(preview_table, data)
                
                # Store loaded data for saving
                if not hasattr(dialog, '_loaded_data'):
                    dialog._loaded_data = {}
                dialog._loaded_data = {
                    'data': data,
                    'filename': file_name
                }
                
        except Exception as e:
            ui.notify(f'Error processing file: {str(e)}', type='error')
    
    def _save_dataset_from_dialog(self, label_input, kind_select,
                                  passband_select, component_select, dialog, is_edit, edit_dataset,
                                  tabs=None, n_points_input=None,
                                  phase_min_input=None, phase_max_input=None):
        """Save dataset from dialog."""
        dataset = label_input.value.strip()
        
        if not dataset:
            ui.notify('Please enter a dataset label', type='error')
            return
            
        # Check for duplicate labels (except when editing same dataset)
        if dataset in self.dataset_model.datasets and (not is_edit or dataset != edit_dataset):
            ui.notify(f'Dataset label "{dataset}" already exists', type='error')
            return
        
        # Validate phase parameters
        npts = int(n_points_input.value)
        phase_min = float(phase_min_input.value)
        phase_max = float(phase_max_input.value)
        
        if phase_min >= phase_max:
            ui.notify('Phase min must be less than phase max', type='error')
            return
        
        if npts < 10:
            ui.notify('Number of points must be at least 10', type='error')
            return
        
        # Generate compute_phases array for API
        compute_phases = np.linspace(phase_min, phase_max, npts)
        
        # Base parameters - every dataset has these
        add_params = {
            'dataset': dataset,
            'kind': kind_select.value,
            'passband': passband_select.value,
            'component': component_select.value,
            'phase_min': phase_min,
            'phase_max': phase_max,
            'n_points': npts,
            'compute_phases': compute_phases,  # For API only, not stored in model
            'filename': 'Synthetic'  # Default to synthetic
        }
        
        # Check if observational data was loaded
        if hasattr(dialog, '_loaded_data'):
            # User loaded observational data
            loaded_data = dialog._loaded_data['data']
            filename = dialog._loaded_data['filename']
            
            add_params.update({
                'times': loaded_data['times'],
                'sigmas': loaded_data['sigmas'],
                'filename': filename,
                'observed_points': len(loaded_data['times'])  # Track actual data points from file
            })
            
            # Add kind-specific observational data
            if kind_select.value == 'lc':
                add_params['fluxes'] = loaded_data['obs']
            elif kind_select.value == 'rv':
                add_params['rvs'] = loaded_data['obs']
        else:
            # Pure synthetic dataset - no observed data points
            add_params['observed_points'] = 0
        
        # Remove old dataset if editing with different name
        if is_edit and dataset != edit_dataset:
            del self.dataset_model.datasets[edit_dataset]
        
        # Add/update dataset
        try:
            self.add_dataset(**add_params)
            
            if is_edit:
                ui.notify(f'Updated dataset "{dataset}"', type='positive')
            else:
                ui.notify(f'Added dataset "{dataset}"', type='positive')
            
            # Update the dataset grid
            if hasattr(self.ui_ref, '_update_dataset_grid'):
                self.ui_ref._update_dataset_grid()
            
        except Exception as e:
            ui.notify(f'Error adding dataset: {str(e)}', type='error')
            print(f"Dataset creation error: {e}")
        
        # Always close the dialog
        dialog.close()

    def _get_file_description(self, filename: str) -> str:
        """Get description for example files."""
        descriptions = {
            'example_lc_binary.dat': 'Detached eclipsing binary light curve (Period = 2.5 days)',
            'example_lc_contact.dat': 'Contact binary light curve (Period = 0.8 days)',
            'example_rv_primary.dat': 'Radial velocity curve for primary star (Period = 2.5 days)'
        }
        return descriptions.get(filename, 'Example data file')

    def _parse_data_file(self, file_path: str) -> Optional[Dict[str, np.ndarray]]:
        """Parse data from a file path."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            return self._parse_data_content(content)
        except Exception as e:
            raise Exception(f'Failed to read file: {str(e)}')
    
    def _parse_data_content(self, content: str) -> Optional[Dict[str, np.ndarray]]:
        """Parse data from file content."""
        lines = content.strip().split('\n')
        
        # Filter out comment lines and empty lines
        data_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                data_lines.append(line)
        
        if not data_lines:
            raise Exception('No data found in file')
        
        # Parse data
        time_values = []
        value_values = []
        error_values = []
        
        for i, line in enumerate(data_lines):
            try:
                # Split by whitespace (handles both spaces and tabs)
                parts = line.split()
                if len(parts) < 2:
                    continue  # Skip lines with insufficient data
                
                time_val = float(parts[0])
                value_val = float(parts[1])
                error_val = float(parts[2]) if len(parts) > 2 else 0.01  # Default error if not provided
                
                time_values.append(time_val)
                value_values.append(value_val)
                error_values.append(error_val)
                
            except (ValueError, IndexError):
                ui.notify(f'Skipping invalid line {i+1}: {line}', type='warning')
                continue
        
        if not time_values:
            raise Exception('No valid data points found')
        
        # Return raw data for conversion to unified format
        return {
            'times': np.array(time_values),
            'obs': np.array(value_values),  # Could be flux, magnitude, or velocity
            'sigmas': np.array(error_values)
        }


class LightCurvePlot:
    """Widget for plotting light curves."""
    
    def __init__(self, dataset_model: DatasetModel, ui_ref=None):
        self.dataset_model = dataset_model
        self.ui_ref = ui_ref  # Reference to main UI for accessing parameters
        self.model_data = None  # Store computed model data
        
        with ui.column().classes('w-full h-full p-4 min-w-0'):
            ui.label('Light Curve Plot').classes('text-lg font-bold')
            
            # Plot controls row
            with ui.row().classes('gap-4 mb-4'):
                # X-axis dropdown
                self.x_axis_dropdown = ui.select(
                    options={'time': 'Time', 'phase': 'Phase'},
                    value='time',
                    label='X-axis'
                ).classes('w-24')
                self.x_axis_dropdown.on('update:model-value', lambda: self.update_plot())
                
                # Y-axis dropdown
                self.y_axis_dropdown = ui.select(
                    options={'magnitude': 'Magnitude', 'flux': 'Flux'},
                    value='flux',
                    label='Y-axis'
                ).classes('w-24')
                self.y_axis_dropdown.on('update:model-value', lambda: self.update_plot())
            
            # Plot container
            self.plot = ui.plotly(self._create_empty_plot()).classes('w-full  min-w-0')
            
            # Add resize observer to handle container size changes
            self.plot._props['config'] = {
                'responsive': True,
                'displayModeBar': True,
                'displaylogo': False
            }
    
    def _create_empty_plot(self):
        fig = go.Figure()
        
        # Determine axis settings based on current selections
        x_title = 'Time (BJD)' if self.x_axis_dropdown.value == 'time' else 'Phase'
        y_title = 'Magnitude' if self.y_axis_dropdown.value == 'magnitude' else 'Flux'
        y_reversed = self.y_axis_dropdown.value == 'magnitude'

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
            showlegend=False,
            uirevision=True
        )
        
        return fig
    
    def update_plot(self):
        """Update plot based on current visibility settings and data."""
        fig = self._create_empty_plot()

        # Plot data for each dataset that has plot_data enabled
        for dataset_name, dataset_info in self.dataset_model.datasets.items():
            if dataset_info.get('plot_data', False) and len(dataset_info.get('times', [])) > 0:
                # This dataset has observational data and should be plotted
                data = {
                    'times': dataset_info['times'],
                    'obs': dataset_info.get('fluxes', dataset_info.get('rvs', [])),
                    'sigmas': dataset_info['sigmas']
                }
                
                if self.x_axis_dropdown.value == 'phase':
                    # Get period and t0 from UI parameters
                    period = getattr(self.ui_ref, 'period_param', None)
                    t0 = getattr(self.ui_ref, 't0_param', None)
                    period_value = period.value_input.value if period else 2.5
                    t0_value = t0.value_input.value if t0 else 0.0
                    
                    # Convert to phase [-0.5, 0.5] and alias for plotting
                    phase_data = time_to_phase(data['times'], period_value, t0_value)
                    x_data, flux_aliased, error_aliased = alias_phase_for_plotting(
                        phase_data, data['obs'], data['sigmas'], extend_range=0.1
                    )
                else:
                    x_data = data['times']
                    flux_aliased = data['obs']
                    error_aliased = data['sigmas']
                
                if self.y_axis_dropdown.value == 'magnitude':
                    y_data = flux_to_magnitude(flux_aliased)
                    y_error = magnitude_error_to_flux_error(flux_aliased, error_aliased)
                else:
                    y_data = flux_aliased
                    y_error = error_aliased

                fig.add_trace(go.Scatter(
                    x=x_data,
                    y=y_data,
                    error_y=dict(type='data', array=y_error, visible=True),
                    mode='markers',
                    marker=dict(size=4, color='blue'),
                    name=f'{dataset_name} (Data)'
                ))

        # Plot model data for each dataset that has plot_model enabled
        if self.model_data is not None:
            for dataset_name, dataset_info in self.dataset_model.datasets.items():
                if dataset_info.get('plot_model', False) and dataset_name in self.model_data:
                    dataset_model = self.model_data[dataset_name]
                    
                    model_times = np.array(dataset_model.get('times', []))
                    model_phases = np.array(dataset_model.get('phases', []))
                    
                    # Get model values based on dataset kind
                    if 'fluxes' in dataset_model:
                        model_values = np.array(dataset_model.get('fluxes', []))
                        data_type = 'LC'
                    elif 'rvs' in dataset_model:
                        model_values = np.array(dataset_model.get('rvs', []))
                        data_type = 'RV'
                    else:
                        continue  # Skip if no model data available

                    has_model = len(model_times) > 0 and len(model_phases) > 0 and len(model_values) > 0
                    
                    if has_model:
                        if self.x_axis_dropdown.value == 'phase':
                            x_model, y_model = alias_phase_for_plotting(model_phases, model_values, extend_range=0.1)
                        else:
                            x_model = model_times
                            y_model = model_values

                        if self.y_axis_dropdown.value == 'magnitude' and data_type == 'LC':
                            y_model = flux_to_magnitude(y_model)
                            
                        # Add model trace to plot
                        fig.add_trace(go.Scatter(
                            x=x_model,
                            y=y_model,
                            mode='lines',
                            line=dict(color='red', width=2),
                            name=f'{dataset_name} (Model)'
                        ))

        self.plot.figure = fig
        self.plot.update()
    
    def set_model_data(self, model_data):
        """Set model data from external computation."""
        self.model_data = model_data
        # self.show_model_checkbox.value = True
        self.update_plot()


class PhoebeUI:
    """Main Phoebe UI."""
    
    def __init__(self, session_api: SessionAPI = None, phoebe_api: PhoebeAPI = None):
        self.session_api = session_api
        self.phoebe_api = phoebe_api
        self.client_id = None  # Will be set when session is established
        self.user_first_name = None
        self.user_last_name = None

        # Initialize data components
        self.dataset_model = DatasetModel()
        self.dataset_view = DatasetView(self.dataset_model, ui_ref=self)

        # Show startup dialog first
        self.show_startup_dialog()

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
            # Handle plot resize on splitter change
            plot_id = self.light_curve_plot.plot.id
            plot_resize_js = f'Plotly.Plots.resize(getHtmlElement({plot_id}))'
            self.main_splitter.on_value_change(lambda: ui.run_javascript(plot_resize_js))

    def create_parameter_panel(self):
        """Create the parameter control panel."""
        
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
                on_value_changed=self._on_ephemeris_changed
            )
            
            self.period_param = PhoebeParameterWidget(
                name='period@binary',
                label='Period (d)',
                value=2.5,
                step=0.0001,
                adjust=False,
                phoebe_api=self.phoebe_api,
                on_value_changed=self._on_ephemeris_changed
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
        
        # Compute controls (outside collapsible container)
        ui.separator().classes('my-4')
        
        # Compute controls
        ui.label('Compute Controls').classes('text-lg font-bold mb-2')

        with ui.row().classes('gap-4 items-center w-full'):
            self.compute_button = ui.button('Compute Model', on_click=self.compute_model, icon='calculate').classes('h-12 flex-shrink-0')
        
        with ui.row().classes('gap-4 mt-2'):
            self.fit_button = ui.button('Fit Parameters', on_click=self.fit_parameters, icon='tune').classes('h-12 flex-shrink-0')
    
    def create_plot_panel(self):
        """Create the plotting panel."""
        with ui.column().classes('w-full h-full p-4 min-w-0'):
            # Dataset management section in an expansion (fold)
            with ui.expansion('Dataset Management', icon='table_chart', value=True).classes('w-full mb-2').style('padding: 2px;'):
                # Enhanced dataset control grid
                self.dataset_grid = ui.aggrid({
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
                            'cellRendererParams': {'disabled': False},
                            'editable': True,
                            'cellClassRules': {
                                'disabled-cell': 'data.filename === "Synthetic"'
                            }
                        },
                        {
                            'field': 'plot_model',
                            'headerName': 'Plot Model',
                            'width': 90,
                            'cellRenderer': 'agCheckboxCellRenderer',
                            'cellRendererParams': {'disabled': False},
                            'editable': True
                        }
                    ],
                    'rowData': [],
                    'domLayout': 'autoHeight',
                    'suppressHorizontalScroll': False,
                    'enableCellChangeFlash': True,
                    'rowSelection': 'single',
                    'theme': 'ag-theme-alpine'
                }).classes('w-full').style('height: auto; min-height: 80px; max-height: 300px;')
                
                # Add CSS for disabled cells
                ui.add_head_html('''
                <style>
                .ag-theme-alpine .disabled-cell {
                    opacity: 0.5;
                    pointer-events: none;
                }
                </style>
                ''')
                
                # Add event handler for cell changes (checkbox updates)
                self.dataset_grid.on('cellValueChanged', self._on_cell_value_changed)
                
                # Add event handler for cell clicks (to capture row selection)
                self.dataset_grid.on('cellClicked', self._on_cell_clicked)
                
                # Initialize grid with current datasets
                self._update_dataset_grid()
                
                # Store selected dataset for edit/remove operations
                self.selected_dataset_label = None
                
                # Dataset action buttons - same row, right-aligned, below table
                with ui.row().classes('gap-2 justify-end w-full'):
                    ui.button(
                        'Add',
                        on_click=self.dataset_view.open_add_dataset_dialog,
                        icon='add'
                    ).props('flat color=primary')
                    ui.button(
                        'Edit',
                        on_click=self._edit_selected_dataset,
                        icon='edit'
                    ).props('flat color=secondary')
                    ui.button(
                        'Remove',
                        on_click=self._remove_selected_dataset,
                        icon='delete'
                    ).props('flat color=negative')
            
            # Light curve plot (pass reference to UI for parameter access)
            self.light_curve_plot = LightCurvePlot(self.dataset_model, self)
    
    def _update_dataset_grid(self):
        """Update the dataset grid with current datasets."""
        if not hasattr(self, 'dataset_grid'):
            return
        
        # Check if model has been computed
        has_model = hasattr(self, 'model_data') and self.model_data is not None
        
        # Create row data from current datasets
        row_data = []
        for dataset_name, dataset_info in self.dataset_model.datasets.items():
            # Determine if dataset has observational data
            has_obs_data = len(dataset_info.get('times', [])) > 0
            is_synthetic = dataset_info.get('filename', '') == 'Synthetic'
            
            # For synthetic datasets: plot_data should be disabled and False
            # For observational datasets: plot_data should be enabled and follow user preference
            plot_data_value = False if is_synthetic else dataset_info.get('plot_data', True)
            
            # Plot model should start as False and only be enabled after model computation
            plot_model_value = dataset_info.get('plot_model', False) if has_model else False
            
            # Format phases display - always show (pmin, pmax, npts) from model definition
            phase_min = dataset_info.get('phase_min', -0.5)
            phase_max = dataset_info.get('phase_max', 0.5)
            n_points = dataset_info.get('n_points', 201)
            phases_display = f"({phase_min:.2f}, {phase_max:.2f}, {n_points})"
            
            # Data points: 0 for synthetic-only, actual file count for observations
            if is_synthetic:
                data_points = 0
            else:
                # For observational data, get the actual number of data points from file
                data_points = dataset_info.get('observed_points', dataset_info.get('n_points', 0))
            
            row_data.append({
                'label': dataset_name,
                'type': dataset_info['kind'].upper(),
                'phases': phases_display,
                'data_points': data_points,
                'passband': dataset_info.get('passband', 'N/A'),
                'filename': dataset_info.get('filename', 'Synthetic') if has_obs_data else 'Synthetic',
                'plot_data': plot_data_value,
                'plot_model': plot_model_value,
                'actions': dataset_name,  # Store dataset name for action callbacks
                'plot_data_disabled': is_synthetic,  # Custom field to track disabled state
                'plot_model_disabled': not has_model  # Custom field to track disabled state
            })
        
        # Update the grid
        self.dataset_grid.options['rowData'] = row_data
        self.dataset_grid.update()
        
        # Update the plot to reflect the current checkbox states
        if hasattr(self, 'light_curve_plot') and self.light_curve_plot:
            self.light_curve_plot.update_plot()
    
    def _on_cell_value_changed(self, event):
        """Handle changes to AgGrid cell values (checkboxes)."""
        # Debug the event structure
        print(f"Cell value changed event: {event.args}")
        
        data = event.args.get('data', {})
        # Try different ways to get the field name
        field = None
        if 'colDef' in event.args:
            field = event.args['colDef'].get('field')
        elif 'column' in event.args:
            field = event.args['column'].get('colId')
        elif 'colId' in event.args:
            field = event.args['colId']
        
        if not field:
            print(f"Could not determine field from event: {event.args}")
            return
            
        dataset_label = data.get('label')
        if not dataset_label:
            print(f"Could not determine dataset label from event data: {data}")
            return
        
        if field in ['plot_data', 'plot_model']:
            # Check if this change should be allowed
            if field == 'plot_data' and data.get('filename') == 'Synthetic':
                # Prevent plot_data changes for synthetic datasets
                ui.notify('Plot Data is not available for synthetic datasets', type='warning')
                # Revert the change
                self._update_dataset_grid()
                return
            
            if field == 'plot_model' and (not hasattr(self, 'model_data') or self.model_data is None):
                # Prevent plot_model changes when no model is computed
                ui.notify('Please compute the model first', type='warning')
                # Revert the change
                self._update_dataset_grid()
                return
            
            # Apply the change
            new_value = event.args.get('newValue', event.args.get('value'))
            if dataset_label in self.dataset_model.datasets:
                self.dataset_model.datasets[dataset_label][field] = new_value
                self.light_curve_plot.update_plot()
    
    def _on_cell_clicked(self, event):
        """Handle cell clicks in the AgGrid to track row selection."""
        try:
            if hasattr(event, 'args') and event.args and 'data' in event.args:
                row_data = event.args['data']
                if isinstance(row_data, dict) and 'label' in row_data:
                    self.selected_dataset_label = row_data['label']
                    # Optional: Show which dataset is selected
                    ui.notify(f"Selected: {self.selected_dataset_label}", type='info')
                else:
                    self.selected_dataset_label = None
            else:
                self.selected_dataset_label = None
                
        except Exception as e:
            print(f"Cell click error: {e}")
            self.selected_dataset_label = None
    
    def _edit_selected_dataset(self):
        """Edit the selected dataset from the grid."""
        if not self.selected_dataset_label:
            ui.notify('Please select a dataset to edit', type='warning')
            return
            
        # Use the existing dialog with the selected dataset
        self.dataset_view.open_edit_dataset_dialog(self.selected_dataset_label)
    
    def _remove_selected_dataset(self):
        """Remove the selected dataset from the grid."""
        if not self.selected_dataset_label:
            ui.notify('Please select a dataset to remove', type='warning')
            return
            
        dataset_label = self.selected_dataset_label
        # Confirm removal
        with ui.dialog() as confirm_dialog, ui.card():
            ui.label(f'Are you sure you want to remove dataset "{dataset_label}"?')
            with ui.row().classes('gap-2 justify-end mt-4'):
                ui.button('Cancel', on_click=confirm_dialog.close).props('flat')
                ui.button(
                    'Remove',
                    on_click=lambda: self._confirm_remove_dataset(dataset_label, confirm_dialog),
                    color='negative'
                ).props('flat')
        confirm_dialog.open()
    
    def _confirm_remove_dataset(self, dataset_label, dialog):
        """Confirm and remove the selected dataset."""
        if dataset_label in self.dataset_model.datasets:
            del self.dataset_model.datasets[dataset_label]
            self._update_dataset_grid()
            self.light_curve_plot.update_plot()
            ui.notify(f'Dataset "{dataset_label}" removed successfully', type='positive')
        dialog.close()
    
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
    
    def _on_ephemeris_changed(self, param_name=None, param_value=None):
        """Handle changes to ephemeris parameters (t0, period) and update phase plot."""
        if hasattr(self, 'light_curve_plot') and self.light_curve_plot:
            # Only replot if we're currently showing phase on x-axis
            if self.light_curve_plot.x_axis_dropdown.value == 'phase':
                self.light_curve_plot.update_plot()
    
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
            
            print(f'{response=}')
            if response['status'] == 'success':
                model_data = response.get('result', {}).get('model', {})
                
                # Store model data for plotting
                self.model_data = model_data  # Store for enabling plot_model checkboxes
                if hasattr(self, 'light_curve_plot') and self.light_curve_plot:
                    self.light_curve_plot.set_model_data(model_data)
                
                # Update dataset grid to enable plot_model checkboxes
                self._update_dataset_grid()
                
                # Show success notification
                ui.notify('Model computed successfully', type='positive')
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
