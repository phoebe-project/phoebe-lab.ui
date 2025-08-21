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
                 adjust: bool = False, on_value_changed=None):
        self.name = name
        self.label = label
        self.value = value
        self.step = step
        self.adjust = adjust
        self.on_value_changed = on_value_changed  # Callback for value changes
        
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
            
            # Add value change handler if provided
            if self.on_value_changed:
                def handle_change():
                    self.on_value_changed(self.name, self.value_input.value)
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


class DataTable:
    """
    Widget for displaying and managing datasets.
    """

    def __init__(self, ui_ref=None):
        self.datasets = {}  # Dictionary to store multiple datasets: {label: dataset_info}
        self.ui_ref = ui_ref  # Reference to main UI for accessing API and parameters

        with ui.column().classes('w-full'):
            # Main datasets table
            self.datasets_table = ui.table(
                columns=[
                    {'name': 'dataset', 'label': 'Dataset', 'field': 'dataset', 'align': 'left'},
                    {'name': 'kind', 'label': 'Data Type', 'field': 'kind', 'align': 'left'},
                    {'name': 'passband', 'label': 'Passband', 'field': 'passband', 'align': 'left'},
                    {'name': 'length', 'label': 'Data Points', 'field': 'length', 'align': 'center'}
                ],
                rows=[],
                row_key='dataset',
                selection='single'
            ).classes('w-full').style(
                '--q-table-selection-color: transparent; '
                '--q-table-selected-color: rgba(0,0,0,0);'
            )

            # Hide the selection info text
            self.datasets_table.props('hide-selected-banner')

            # Add dataset action buttons aligned with table
            with ui.row().classes('gap-2 mt-2 w-full justify-end'):
                ui.button(
                    'Add',
                    on_click=self.open_add_dataset_dialog,
                    icon='add'
                ).props('flat color=primary')
                self.edit_button = ui.button(
                    'Edit',
                    on_click=self._edit_selected_dataset,
                    icon='edit'
                ).props('flat color=secondary')
                self.remove_button = ui.button(
                    'Remove',
                    on_click=self._remove_selected_dataset,
                    icon='delete'
                ).props('flat color=negative')

                # Bind button states to selection and data availability
                self._update_button_states()

                # Add selection change handler to update button states
                self.datasets_table.on('selection', lambda _: self._update_button_states())
                # Also handle row clicks to ensure state updates
                self.datasets_table.on('rowClick', lambda _: self._update_button_states())

    def _update_button_states(self):
        """Update the enabled/disabled state of edit and remove buttons."""
        has_data = len(self.datasets) > 0
        
        # Check if we have a valid selection
        try:
            selected = getattr(self.datasets_table, 'selected', [])
            has_selection = selected and len(selected) > 0
        except Exception:
            has_selection = False
        
        # Enable buttons only if there is data and a selection
        button_enabled = has_data and has_selection
        
        if hasattr(self, 'edit_button'):
            if button_enabled:
                self.edit_button.enable()
                self.edit_button.props('flat color=secondary')
            else:
                self.edit_button.disable()
                self.edit_button.props('flat color=grey-5')
                
        if hasattr(self, 'remove_button'):
            if button_enabled:
                self.remove_button.enable()
                self.remove_button.props('flat color=negative')
            else:
                self.remove_button.disable()
                self.remove_button.props('flat color=grey-5')
    
    def _remove_selected_dataset(self):
        """Remove the currently selected dataset."""
        try:
            selected = self.datasets_table.selected
            if not selected or len(selected) == 0:
                ui.notify('Please select a dataset to remove', type='warning')
                return
            
            # Get the selected row's label
            selected_dataset = selected[0].get('dataset') if hasattr(selected[0], 'get') else selected[0].get('dataset', '')
            
            if selected_dataset and selected_dataset in self.datasets:
                # Show confirmation dialog
                with ui.dialog() as confirm_dialog, ui.card():
                    ui.label(f'Remove Dataset: {selected_dataset}').classes('text-lg font-bold mb-4')
                    ui.label('Are you sure you want to remove this dataset? '
                             'This action cannot be undone.').classes('mb-4')
                    
                    with ui.row().classes('gap-2 justify-end w-full'):
                        ui.button('Cancel', on_click=confirm_dialog.close).classes('bg-gray-500')
                        ui.button(
                            'Remove',
                            on_click=lambda: [
                                self.remove_dataset(selected_dataset),
                                confirm_dialog.close(),
                                ui.timer(0.1, lambda: self._update_button_states(), once=True)
                            ],
                            icon='delete'
                        ).classes('bg-red-500')
                
                confirm_dialog.open()
            else:
                ui.notify('Selected dataset not found', type='error')
                
        except Exception as e:
            print(f"Error removing selected dataset: {e}")
            ui.notify('Error removing dataset', type='error')

    def _edit_selected_dataset(self):
        """Edit the currently selected dataset."""
        try:
            selected = self.datasets_table.selected
            if not selected or len(selected) == 0:
                ui.notify('Please select a dataset to edit', type='warning')
                return
            
            # Get the selected row's label
            selected_dataset = selected[0].get('dataset') if hasattr(selected[0], 'get') else selected[0].get('dataset', '')
            
            if selected_dataset and selected_dataset in self.datasets:
                self._open_dataset_dialog(edit_dataset=selected_dataset)
            else:
                ui.notify('Selected dataset not found', type='error')
                
        except Exception as e:
            print(f"Error editing selected dataset: {e}")
            ui.notify('Error editing dataset', type='error')

    def open_add_dataset_dialog(self):
        """Open dialog to add a new dataset."""
        self._open_dataset_dialog()
    
    def open_edit_dataset_dialog(self, dataset: str):
        """Open dialog to edit an existing dataset."""
        if dataset in self.datasets:
            self._open_dataset_dialog(edit_dataset=dataset)
    
    def _open_dataset_dialog(self, edit_dataset: str = None):
        """Open dialog to add or edit a dataset."""
        is_edit = edit_dataset is not None
        existing_dataset = self.datasets.get(edit_dataset) if is_edit else None
        
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
                
                # Data label input
                label_input = ui.input(
                    label='Data Label',
                    placeholder='e.g., lc01, rv_primary, etc.',
                    value=edit_dataset if is_edit else f'dataset_{len(self.datasets) + 1:02d}'
                ).classes('w-full')
                
                # Passband selection
                passband_select = ui.select(
                    options=['GoChile:R', 'GoChile:G', 'GoChile:B', 'GoChile:L', 'Johnson:V', 'Johnson:B'],
                    value=existing_dataset['passband'] if is_edit else 'GoChile:R',
                    label='Passband'
                ).classes('w-full')
                
                # Component selection (for RV datasets)
                component_select = ui.select(
                    options={
                        'primary': 'Primary',
                        'secondary': 'Secondary'
                    },
                    value=existing_dataset.get('component', 'primary') if is_edit else 'primary',
                    label='Component (for RV data)'
                ).classes('w-full')
                
                # Show/hide component selector based on kind
                def update_component_visibility():
                    component_select.visible = kind_select.value == 'rv'
                
                kind_select.on('update:model-value', lambda: update_component_visibility())
                update_component_visibility()  # Set initial visibility

            ui.separator().classes('my-4')
            
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
            
            # Data preview section (collapsible, collapsed by default)
            # ui.separator().classes('my-4')
            
            with ui.expansion('Data Preview', icon='table_view').classes('w-full') as preview_expansion:
                preview_expansion.open = False  # Collapsed by default
                
                preview_container = ui.column().classes('w-full')
                
                with preview_container:
                    preview_label = ui.label('No data loaded').classes('text-sm text-gray-600 mb-2')
                    if is_edit:
                        preview_label.text = f'{existing_dataset["filename"]} ({existing_dataset["length"]} points)'
                    
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
                if is_edit:
                    self._populate_preview_table(preview_table, existing_dataset['data'])
            
            # Dialog buttons
            ui.separator().classes('my-4')
            with ui.row().classes('gap-2 justify-end w-full'):
                ui.button('Cancel', on_click=dataset_dialog.close).classes('bg-gray-500')
                ui.button(
                    'Save' if is_edit else 'Add',
                    on_click=lambda: self._save_dataset_from_dialog(
                        label_input, kind_select, passband_select, component_select,
                        dataset_dialog, is_edit, edit_dataset
                    ),
                    icon='save'
                ).classes('bg-blue-500')
        
        dataset_dialog.open()
    
    def _populate_preview_table(self, preview_table, data):
        """Populate preview table with dataset."""
        rows = []
        display_count = min(20, len(data['times']))
        value_key = 'obs' if 'obs' in data else 'value'
        
        for i in range(display_count):
            rows.append({
                'time': round(float(data['times'][i]), 4),
                'value': round(float(data[value_key][i]), 4),
                'error': round(float(data['sigmas'][i]), 4)
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
                                 passband_select, component_select, dialog, is_edit, edit_dataset):
        """Save dataset from dialog."""
        dataset = label_input.value.strip()
        
        if not dataset:
            ui.notify('Please enter a dataset label', type='error')
            return
            
        # Check for duplicate labels (except when editing same dataset)
        if dataset in self.datasets and (not is_edit or dataset != edit_dataset):
            ui.notify(f'Dataset label "{dataset}" already exists', type='error')
            return
        
        # Get data (either loaded new data or use existing)
        if hasattr(dialog, '_loaded_data'):
            data_info = dialog._loaded_data
        elif is_edit and edit_dataset in self.datasets:
            # Use existing data if no new data loaded
            existing = self.datasets[edit_dataset]
            data_info = {
                'data': existing['data'],
                'filename': existing['filename']
            }
        else:
            ui.notify('To add a dataset, you need to load the data first.', type='error')
            return
        
        if is_edit:
            # If label changed, remove old dataset and add with new label
            if dataset != edit_dataset:
                # Remove old dataset
                del self.datasets[edit_dataset]
                # Add with new label
                self._add_dataset(
                    dataset=dataset,
                    kind=kind_select.value,
                    passband=passband_select.value,
                    data=data_info['data'],
                    filename=data_info['filename'],
                    component=component_select.value
                )
                ui.notify(f'Dataset renamed from "{edit_dataset}" to "{dataset}"', type='positive')
            else:
                # Update existing dataset with same label
                self.datasets[edit_dataset]['kind'] = kind_select.value
                self.datasets[edit_dataset]['passband'] = passband_select.value
                self.datasets[edit_dataset]['component'] = component_select.value
                self.datasets[edit_dataset]['data'] = data_info['data']
                self.datasets[edit_dataset]['filename'] = data_info['filename']
                self.datasets[edit_dataset]['length'] = len(data_info['data']['times'])
                ui.notify(f'Updated dataset "{edit_dataset}"', type='positive')
        else:
            # Add new dataset
            self._add_dataset(
                dataset=dataset,
                kind=kind_select.value,
                passband=passband_select.value,
                data=data_info['data'],
                filename=data_info['filename'],
                component=component_select.value
            )
        
        dialog.close()
        
        # Update button states after dialog closes (selection may be cleared)
        ui.timer(0.1, lambda: self._update_button_states(), once=True)
    
    def _confirm_remove_dataset(self, dataset, dialog):
        """Show confirmation dialog for dataset removal."""
        with ui.dialog() as confirm_dialog, ui.card():
            ui.label(f'Remove Dataset: {dataset}').classes('text-lg font-bold mb-4')
            ui.label('Are you sure you want to remove this dataset? '
                     'This action cannot be undone.').classes('mb-4')
            
            with ui.row().classes('gap-2 justify-end w-full'):
                ui.button('Cancel', on_click=confirm_dialog.close).classes('bg-gray-500')
                ui.button('Remove', on_click=lambda: [
                    self.remove_dataset(dataset),
                    confirm_dialog.close(),
                    dialog.close()
                ]).classes('bg-red-500')
        
        confirm_dialog.open()

    def _get_file_description(self, filename: str) -> str:
        """Get description for example files."""
        descriptions = {
            'example_lc_binary.dat': 'Detached eclipsing binary light curve (Period = 2.5 days)',
            'example_lc_contact.dat': 'Contact binary light curve (Period = 0.8 days)',
            'example_rv_primary.dat': 'Radial velocity curve for primary star (Period = 2.5 days)'
        }
        return descriptions.get(filename, 'Example data file')
    
    def _load_example_file(self, file_path: str, dialog, label_input, kind_select, passband_select, component_select):
        """Load an example file and add to datasets."""
        try:
            data = self._parse_data_file(file_path)
            if data:
                self._add_dataset(
                    dataset=label_input.value,
                    kind=kind_select.value,
                    passband=passband_select.value,
                    data=data,
                    filename=Path(file_path).name,
                    component=component_select.value
                )
                dialog.close()
        except Exception as e:
            ui.notify(f'Error loading example file: {str(e)}', type='error')
    
    def _handle_file_upload(self, event, dialog, label_input, kind_select, passband_select, component_select):
        """Handle uploaded file and add to datasets."""
        try:
            # Get uploaded file content
            file_content = event.content.read()
            file_name = event.name
            
            # Convert bytes to string
            if isinstance(file_content, bytes):
                file_content = file_content.decode('utf-8')
            
            # Parse the content
            data = self._parse_data_content(file_content)
            if data:
                self._add_dataset(
                    dataset=label_input.value,
                    kind=kind_select.value,
                    passband=passband_select.value,
                    data=data,
                    filename=file_name,
                    component=component_select.value
                )
                dialog.close()
                
        except Exception as e:
            ui.notify(f'Error processing uploaded file: {str(e)}', type='error')
    
    def _add_dataset(self, dataset: str, kind: str, passband: str, data: Dict[str, np.ndarray], filename: str, component: str = 'primary'):
        """Add a dataset to the collection."""
        # Validate dataset uniqueness
        if dataset in self.datasets:
            ui.notify(f'Dataset "{dataset}" already exists. Please choose a different name.', type='error')
            return
        
        # Store dataset
        dataset_info = {
            'kind': kind,
            'passband': passband,
            'component': component,
            'dataset': dataset,
            'data': data,
            'filename': filename,
            'length': len(data['times'])
        }
        
        self.datasets[dataset] = dataset_info
        
        # Update datasets table
        self._update_datasets_table()
        
        # Update button states
        self._update_button_states()

        # Call the API to add the dataset to the bundle:
        api = self.ui_ref.phoebe_api
        
        # Prepare parameters for the dataset (excluding kind which goes as positional arg)
        params = {
            'dataset': dataset,
            'passband': passband,
            'times': data['times'],
            'sigmas': data['sigmas'],
            'overwrite': True
        }

        # Add kind-specific parameters
        if kind == 'lc':
            params['fluxes'] = data['obs']
        elif kind == 'rv':
            params['component'] = component
            params['rvs'] = data['obs']

        # Call API with kind as positional argument and rest as kwargs
        api.add_dataset(kind, **params)

        ui.notify(f'Added dataset "{dataset}" with {len(data["times"])} data points', type='positive')
    
    def _update_datasets_table(self):
        """Update the main datasets table."""
        rows = []
        for label, info in self.datasets.items():
            rows.append({
                'dataset': label,
                'kind': info['kind'].replace('_', ' ').upper(),
                'passband': info['passband'],
                'length': info['length']
            })
        
        self.datasets_table.rows = rows
        self.datasets_table.update()
        
        # Clear selection when table is updated
        self.datasets_table.selected = []
        
        # Update button states whenever table is updated
        ui.timer(0.1, lambda: self._update_button_states(), once=True)
    
    def remove_dataset(self, dataset: str):
        """Remove a dataset from the collection."""
        if dataset in self.datasets:
            del self.datasets[dataset]
            self._update_datasets_table()
            
            # Update button states
            self._update_button_states()
            
            ui.notify(f'Removed dataset "{dataset}"', type='info')
    
    def get_dataset(self, dataset: str) -> Optional[Dict]:
        """Get dataset by dataset name."""
        return self.datasets.get(dataset)
    
    def get_all_datasets(self) -> Dict[str, Dict]:
        """Get all datasets."""
        return self.datasets.copy()
    
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
        
        return {
            'times': np.array(time_values),
            'obs': np.array(value_values),  # Could be flux, magnitude, or velocity
            'sigmas': np.array(error_values)
        }
    
    def get_plotting_data(self):
        """Get data for plotting (returns first available dataset for backward compatibility)."""
        if not self.datasets:
            return None
            
        # Return first dataset for plotting
        first_dataset = next(iter(self.datasets.values()))
        return first_dataset['data']


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
        if self.show_model_checkbox.value and self.model_data is None:
            ui.notify('Model has not been computed yet. Use "Compute Model" first.', type='warning')
            self.show_model_checkbox.value = False
            return

        fig = self._create_empty_plot()

        # Add data trace if requested and available
        plotting_data = self.data_table.get_plotting_data()
        if self.show_data_checkbox.value and plotting_data is not None:
            data = plotting_data
            
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
                name=next(iter(self.data_table.datasets.keys())) if self.data_table.datasets else 'Data'
            ))

        # Add model trace if requested and available
        if self.show_model_checkbox.value and self.model_data is not None:
            if self.x_axis_dropdown.value == 'phase':
                # Get period and t0 from UI parameters
                period = getattr(self.ui_ref, 'period_param', None)
                t0 = getattr(self.ui_ref, 't0_param', None)
                period_value = period.value_input.value if period else 2.5
                t0_value = t0.value_input.value if t0 else 0.0
                
                # Convert to phase [-0.5, 0.5] and alias for plotting
                phase_model = time_to_phase(self.model_data['times'], period_value, t0_value)
                x_model, flux_model_aliased = alias_phase_for_plotting(
                    phase_model, self.model_data['obs'], extend_range=0.1
                )
            else:
                x_model = self.model_data['times']
                flux_model_aliased = self.model_data['obs']
                
            if self.y_axis_dropdown.value == 'magnitude':
                y_model = flux_to_magnitude(flux_model_aliased)
            else:
                y_model = flux_model_aliased

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
            self.data_table = DataTable(ui_ref=self)
        
        # Ephemerides parameters
        with ui.expansion('Ephemerides', icon='schedule', value=False).classes('w-full mb-4'):
            # Create parameter widgets for t0 and period
            self.t0_param = PhoebeParameterWidget(
                name='t0',
                label='T₀ (BJD)',
                value=2458000.0,
                step=0.01,
                adjust=False,
                on_value_changed=self._on_ephemeris_changed
            )
            
            self.period_param = PhoebeParameterWidget(
                name='period',
                label='Period (d)',
                value=2.5,
                step=0.0001,
                adjust=False,
                on_value_changed=self._on_ephemeris_changed
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
            ui.button('Fit Parameters', on_click=self.fit_parameters, icon='tune').classes('h-12 flex-shrink-0')
    
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
    
    def compute_model(self):
        """Compute Phoebe model with current parameters."""
        response = self.phoebe_api.run_command('b.run_compute', params={})
        if response['status'] == 'success':
            ui.notify('Model computed successfully', type='positive')
        else:
            ui.notify(f"Model computation failed: {response['error']}", type='error')

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
