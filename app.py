import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
from data_handler import (
    parse_uploaded_file, 
    extract_sales_velocity, 
    extract_initial_inventory, 
    extract_delivery_schedule,
    extract_seasonality_factors,
    generate_sample_data
)
from forecast_logic import (
    run_forecast, 
    analyze_forecast, 
    get_default_seasonality
)
from db_handler import (
    save_forecast,
    get_forecasts,
    get_forecast,
    delete_forecast,
    get_forecasts_by_asin,
    get_unique_asins
)
from weighted_velocity import (
    calculate_daily_velocity,
    calculate_weighted_velocity,
    get_default_periods,
    get_period_days,
    format_period_name,
    get_period_data_table
)

# Set page config
st.set_page_config(
    page_title="Inventory Forecast Simulator",
    page_icon="📊",
    layout="wide"
)

# Application title and description
st.title("📊 Inventory Forecast Simulator")
st.markdown("""
This application helps you simulate daily inventory levels based on sales velocity, 
scheduled deliveries, and reorder logic. Use the controls below to customize your forecast.
""")

# Initialize session state variables if they don't exist
if 'forecast_data' not in st.session_state:
    st.session_state.forecast_data = None
if 'analytics' not in st.session_state:
    st.session_state.analytics = None
if 'uploaded_data' not in st.session_state:
    st.session_state.uploaded_data = None
if 'sales_velocity' not in st.session_state:
    st.session_state.sales_velocity = 44.64  # Default from requirements
if 'initial_inventory' not in st.session_state:
    st.session_state.initial_inventory = 1005  # Default from requirements
if 'deliveries' not in st.session_state:
    # Example deliveries from requirements (day, quantity)
    st.session_state.deliveries = [(44, 2500), (84, 6806)]
if 'seasonality_factors' not in st.session_state:
    st.session_state.seasonality_factors = get_default_seasonality()
if 'lead_time' not in st.session_state:
    st.session_state.lead_time = 80  # Default from requirements
if 'safety_stock_days' not in st.session_state:
    st.session_state.safety_stock_days = 15  # Default from requirements
if 'forecast_params' not in st.session_state:
    st.session_state.forecast_params = None
if 'loaded_forecast' not in st.session_state:
    st.session_state.loaded_forecast = None
if 'use_weighted_velocity' not in st.session_state:
    st.session_state.use_weighted_velocity = False
if 'period_sales' not in st.session_state:
    # Initialize with some default values for all 5 periods
    st.session_state.period_sales = {
        '7_day': 514,    # Example from requirements
        '14_day': 1028,  # Example values (7-day * 2)
        '30_day': 844,   # Example values
        '60_day': 1610,  # Example values
        '90_day': 2335   # Example values
    }
if 'period_weights' not in st.session_state:
    # Initialize with default weights for all 5 periods
    st.session_state.period_weights = {
        '7_day': 0.25,    # Default higher weight to recent data
        '14_day': 0.25,   # Default values
        '30_day': 0.20,   # Default values
        '60_day': 0.15,   # Default values
        '90_day': 0.15    # Default values
    }

# Sidebar for data input and configuration
with st.sidebar:
    st.header("Data Input")
    
    # Data input section with three tabs
    upload_tab, manual_tab, asin_tab = st.tabs(["Upload Data", "Manual Entry", "ASIN/SKU"])
    
    with upload_tab:
        uploaded_file = st.file_uploader("Upload Sales & Inventory Data (CSV or Excel)", type=["csv", "xlsx", "xls"])
        
        if uploaded_file is not None:
            try:
                # Parse the uploaded file
                df = parse_uploaded_file(uploaded_file)
                st.session_state.uploaded_data = df
                
                # Extract key information
                velocity = extract_sales_velocity(df)
                inventory = extract_initial_inventory(df)
                deliveries = extract_delivery_schedule(df)
                seasonal_factors = extract_seasonality_factors(df)
                
                # Update session state
                if velocity > 0:
                    st.session_state.sales_velocity = velocity
                if inventory > 0:
                    st.session_state.initial_inventory = inventory
                if deliveries:
                    st.session_state.deliveries = deliveries
                if seasonal_factors:
                    st.session_state.seasonality_factors = seasonal_factors
                
                st.success(f"Data loaded successfully! Extracted sales velocity: {velocity:.2f} units/day")
                
                # Display data preview
                with st.expander("Preview Uploaded Data"):
                    st.dataframe(df.head())
                    
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")
        
        # Sample data download
        st.download_button(
            label="Download Sample Data Template",
            data=generate_sample_data(),
            file_name="sample_inventory_data.csv",
            mime="text/csv",
            help="Download a sample CSV template to understand the required format"
        )
    
    with manual_tab:
        # Entry mode selection
        entry_mode = st.radio(
            "Entry Mode",
            ["Single Product", "Batch Entry (Multiple Products)"],
            horizontal=True,
            help="Choose single product for detailed entry, or batch entry for multiple products at once"
        )
        
        if entry_mode == "Batch Entry (Multiple Products)":
            st.markdown("### Batch Product Entry")
            st.info("Configure complete forecast settings for up to 4 products, then process all at once.")
            
            import copy
            
            # Number of products to configure
            num_batch_products = st.number_input(
                "Number of Products to Configure",
                min_value=1,
                max_value=4,
                value=2,
                key="num_batch_products",
                help="Set how many products you want to configure (1-4)"
            )
            
            # Initialize batch products state
            def get_default_product_state():
                return {
                    'asin': '',
                    'use_weighted': False,
                    'simple_velocity': 45.0,
                    'period_sales': {'7_day': 0, '14_day': 0, '30_day': 0, '60_day': 0, '90_day': 0},
                    'period_weights': {'7_day': 0.20, '14_day': 0.20, '30_day': 0.20, '60_day': 0.20, '90_day': 0.20},
                    'initial_inventory': 1000,
                    'lead_time': 80,
                    'safety_stock_days': 15,
                    'num_deliveries': 0,
                    'deliveries': []
                }
            
            if 'batch_products' not in st.session_state:
                st.session_state.batch_products = {i: get_default_product_state() for i in range(4)}
            
            # Ensure we have enough product states
            for i in range(4):
                if i not in st.session_state.batch_products:
                    st.session_state.batch_products[i] = get_default_product_state()
            
            # Create tabs for each product
            product_tabs = st.tabs([f"Product {i+1}" for i in range(num_batch_products)])
            
            for prod_idx, prod_tab in enumerate(product_tabs):
                with prod_tab:
                    prod_state = st.session_state.batch_products[prod_idx]
                    
                    # ASIN input
                    prod_state['asin'] = st.text_input(
                        "ASIN/SKU",
                        value=prod_state['asin'],
                        placeholder="Enter ASIN/SKU (e.g., B01234567X)",
                        key=f"batch_asin_{prod_idx}"
                    )
                    
                    # Velocity input method
                    velocity_method = st.radio(
                        "Sales Velocity Input Method",
                        ["Simple", "Weighted Average (Multiple Time Periods)"],
                        index=1 if prod_state['use_weighted'] else 0,
                        horizontal=True,
                        key=f"batch_velocity_method_{prod_idx}"
                    )
                    prod_state['use_weighted'] = (velocity_method == "Weighted Average (Multiple Time Periods)")
                    
                    if not prod_state['use_weighted']:
                        # Simple velocity
                        prod_state['simple_velocity'] = st.number_input(
                            "Daily Sales Velocity (units/day)",
                            min_value=0.1,
                            value=float(prod_state['simple_velocity']),
                            step=0.1,
                            format="%.2f",
                            key=f"batch_simple_vel_{prod_idx}"
                        )
                    else:
                        # Weighted velocity calculator
                        st.markdown("**Sales Data & Weights**")
                        
                        periods_info = [
                            ('7_day', 'Last 7 Days', 7),
                            ('14_day', 'Last 14 Days', 14),
                            ('30_day', 'Last 30 Days', 30),
                            ('60_day', 'Last 60 Days', 60),
                            ('90_day', 'Last 90 Days', 90)
                        ]
                        
                        # Header row
                        hcol1, hcol2, hcol3, hcol4 = st.columns([2, 1, 1, 1])
                        with hcol1:
                            st.markdown("**Period**")
                        with hcol2:
                            st.markdown("**Sales**")
                        with hcol3:
                            st.markdown("**Weight**")
                        with hcol4:
                            st.markdown("**Velocity**")
                        
                        velocities = {}
                        for period_key, period_name, period_days in periods_info:
                            pcol1, pcol2, pcol3, pcol4 = st.columns([2, 1, 1, 1])
                            with pcol1:
                                st.markdown(f"{period_name}")
                            with pcol2:
                                sales = st.number_input(
                                    f"Sales {period_key}",
                                    min_value=0,
                                    value=int(prod_state['period_sales'].get(period_key, 0)),
                                    step=1,
                                    label_visibility="collapsed",
                                    key=f"batch_sales_{prod_idx}_{period_key}"
                                )
                                prod_state['period_sales'][period_key] = sales
                            with pcol3:
                                weight = st.number_input(
                                    f"Weight {period_key}",
                                    min_value=0.0,
                                    max_value=1.0,
                                    value=float(prod_state['period_weights'].get(period_key, 0.25)),
                                    step=0.05,
                                    format="%.2f",
                                    label_visibility="collapsed",
                                    key=f"batch_weight_{prod_idx}_{period_key}"
                                )
                                prod_state['period_weights'][period_key] = weight
                            with pcol4:
                                velocity = sales / period_days if period_days > 0 else 0
                                velocities[period_key] = velocity
                                st.markdown(f"{velocity:.2f}/day")
                        
                        # Calculate weighted velocity
                        total_weight = sum(prod_state['period_weights'].values())
                        if total_weight > 0:
                            weighted_vel = sum(
                                velocities[k] * prod_state['period_weights'][k] 
                                for k in velocities
                            ) / total_weight
                        else:
                            weighted_vel = 0.0
                        
                        st.markdown(f"**Blended Daily Velocity: {weighted_vel:.2f} units/day**")
                        prod_state['calculated_velocity'] = weighted_vel
                    
                    st.markdown("---")
                    
                    # Inventory and lead time
                    inv_col1, inv_col2 = st.columns(2)
                    with inv_col1:
                        prod_state['initial_inventory'] = st.number_input(
                            "Initial Inventory (units)",
                            min_value=0,
                            value=int(prod_state['initial_inventory']),
                            step=1,
                            key=f"batch_inv_{prod_idx}"
                        )
                    with inv_col2:
                        prod_state['lead_time'] = st.number_input(
                            "Lead Time (days)",
                            min_value=1,
                            max_value=365,
                            value=int(prod_state['lead_time']),
                            step=1,
                            key=f"batch_lead_{prod_idx}"
                        )
                    
                    prod_state['safety_stock_days'] = st.number_input(
                        "Safety Stock (days)",
                        min_value=0,
                        max_value=90,
                        value=int(prod_state['safety_stock_days']),
                        step=1,
                        key=f"batch_safety_{prod_idx}"
                    )
                    
                    # Scheduled deliveries
                    st.markdown("**Scheduled Deliveries**")
                    
                    num_del = st.number_input(
                        "Number of Deliveries",
                        min_value=0,
                        max_value=5,
                        value=int(prod_state['num_deliveries']),
                        key=f"batch_num_del_{prod_idx}"
                    )
                    prod_state['num_deliveries'] = num_del
                    
                    # Resize deliveries list
                    while len(prod_state['deliveries']) < num_del:
                        prod_state['deliveries'].append({'day': 30, 'qty': 2500})
                    prod_state['deliveries'] = prod_state['deliveries'][:num_del]
                    
                    for del_idx in range(num_del):
                        del_col1, del_col2 = st.columns(2)
                        with del_col1:
                            day_val = st.number_input(
                                f"Delivery #{del_idx+1} Day",
                                min_value=1,
                                max_value=365,
                                value=int(prod_state['deliveries'][del_idx].get('day', 30)),
                                key=f"batch_del_day_{prod_idx}_{del_idx}"
                            )
                            prod_state['deliveries'][del_idx]['day'] = day_val
                        with del_col2:
                            qty_val = st.number_input(
                                f"Delivery #{del_idx+1} Qty",
                                min_value=1,
                                value=int(prod_state['deliveries'][del_idx].get('qty', 2500)),
                                step=100,
                                key=f"batch_del_qty_{prod_idx}_{del_idx}"
                            )
                            prod_state['deliveries'][del_idx]['qty'] = qty_val
            
            st.markdown("---")
            
            # Shared forecast settings (applied to all products)
            st.markdown("### Shared Forecast Settings (Applied to All Products)")
            
            # Shared Weights Configuration
            with st.expander("Shared Velocity Weight Distribution", expanded=False):
                st.info("Set weights here and click 'Apply to All Products' to use the same weight distribution across all products.")
                
                # Initialize shared weights if not present
                if 'batch_shared_weights' not in st.session_state:
                    st.session_state.batch_shared_weights = {
                        '7_day': 0.25, '14_day': 0.25, '30_day': 0.20, '60_day': 0.15, '90_day': 0.15
                    }
                
                shared_periods = [
                    ('7_day', 'Last 7 Days'),
                    ('14_day', 'Last 14 Days'),
                    ('30_day', 'Last 30 Days'),
                    ('60_day', 'Last 60 Days'),
                    ('90_day', 'Last 90 Days')
                ]
                
                wcol1, wcol2 = st.columns(2)
                for i, (period_key, period_name) in enumerate(shared_periods):
                    with wcol1 if i < 3 else wcol2:
                        st.session_state.batch_shared_weights[period_key] = st.number_input(
                            f"{period_name} Weight",
                            min_value=0.0,
                            max_value=1.0,
                            value=float(st.session_state.batch_shared_weights.get(period_key, 0.20)),
                            step=0.05,
                            format="%.2f",
                            key=f"shared_weight_{period_key}"
                        )
                
                total_shared_weight = sum(st.session_state.batch_shared_weights.values())
                st.caption(f"Total weight: {total_shared_weight:.2f} (will be normalized if not 1.0)")
                
                if st.button("Apply Weights to All Products", type="primary", key="apply_shared_weights"):
                    for prod_idx in range(4):
                        if prod_idx in st.session_state.batch_products:
                            for period_key in st.session_state.batch_shared_weights:
                                st.session_state.batch_products[prod_idx]['period_weights'][period_key] = \
                                    st.session_state.batch_shared_weights[period_key]
                    st.success("Weights applied to all products!")
                    st.rerun()
            
            scol1, scol2 = st.columns(2)
            with scol1:
                batch_forecast_days = st.number_input(
                    "Forecast Days",
                    min_value=30,
                    max_value=365,
                    value=180,
                    key="batch_forecast_days"
                )
            with scol2:
                batch_use_seasonality = st.checkbox(
                    "Apply Seasonality",
                    value=False,
                    key="batch_use_seasonality"
                )
            
            batch_dynamic_reorder = st.checkbox(
                "Enable Dynamic Reordering",
                value=True,
                key="batch_dynamic_reorder"
            )
            
            # Advanced reorder settings
            with st.expander("Advanced Reorder Settings"):
                acol1, acol2 = st.columns(2)
                with acol1:
                    batch_reorder_policy = st.selectbox(
                        "Reorder Policy",
                        options=['R_S', 's_Q', 'EOQ'],
                        index=0,
                        key="batch_reorder_policy",
                        help="R_S: Order-up-to, s_Q: Fixed lot, EOQ: Economic order quantity"
                    )
                    batch_cycle_cover_days = st.number_input(
                        "Cycle Cover Days",
                        min_value=7,
                        max_value=180,
                        value=35,
                        key="batch_cycle_cover_days"
                    )
                    batch_min_days_between = st.number_input(
                        "Min Days Between Orders",
                        min_value=1,
                        max_value=90,
                        value=30,
                        key="batch_min_days_between"
                    )
                    batch_use_service_level = st.checkbox(
                        "Use Service Level Safety Stock",
                        value=False,
                        key="batch_use_service_level",
                        help="Use statistical z-score based safety stock"
                    )
                with acol2:
                    batch_moq = st.number_input(
                        "Minimum Order Quantity",
                        min_value=0,
                        value=0,
                        key="batch_moq"
                    )
                    batch_casepack = st.number_input(
                        "Casepack Multiple",
                        min_value=1,
                        value=1,
                        key="batch_casepack"
                    )
                    batch_stockout_mode = st.selectbox(
                        "Stockout Mode",
                        options=['lost_sales', 'backorders'],
                        index=0,
                        key="batch_stockout_mode"
                    )
                    batch_service_level_z = st.number_input(
                        "Service Level Z-Score",
                        min_value=0.5,
                        max_value=3.5,
                        value=1.65,
                        step=0.05,
                        key="batch_service_level_z",
                        help="Z-score for service level (1.65 = ~95%, 2.05 = ~98%)"
                    )
            
            st.markdown("---")
            
            # Process and Save buttons
            btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
            with btn_col1:
                process_all = st.button("Process All Forecasts", type="primary")
            with btn_col2:
                save_all = st.button("Save All Forecasts", type="secondary")
            
            # Initialize batch results storage
            if 'batch_results' not in st.session_state:
                st.session_state.batch_results = []
            
            if process_all:
                st.session_state.batch_results = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Collect valid products (with ASIN filled)
                valid_products = []
                for i in range(num_batch_products):
                    prod = st.session_state.batch_products[i]
                    if prod['asin'].strip():
                        valid_products.append((i, prod))
                
                if len(valid_products) == 0:
                    st.warning("Please enter at least one ASIN to process forecasts.")
                else:
                    processed_count = 0
                    for prod_idx, prod in valid_products:
                        status_text.text(f"Processing {prod['asin']} ({processed_count + 1}/{len(valid_products)})...")
                        
                        try:
                            from forecast_logic import run_forecast, analyze_forecast
                            
                            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                            
                            # Determine velocity
                            if prod['use_weighted']:
                                velocity = prod.get('calculated_velocity', 0.0)
                            else:
                                velocity = prod['simple_velocity']
                            
                            # Build deliveries list
                            deliveries = [(d['day'], d['qty']) for d in prod['deliveries']]
                            
                            # Deep copy seasonality
                            seasonality_copy = copy.deepcopy(dict(st.session_state.seasonality_factors))
                            
                            # Run forecast
                            forecast_df = run_forecast(
                                initial_inventory=int(prod['initial_inventory']),
                                base_velocity=float(velocity),
                                start_date=start_date,
                                days=batch_forecast_days,
                                deliveries=deliveries,
                                lead_time=int(prod['lead_time']),
                                safety_stock_days=int(prod['safety_stock_days']),
                                use_seasonality=batch_use_seasonality,
                                seasonality_factors=seasonality_copy,
                                dynamic_reorder=batch_dynamic_reorder,
                                reorder_policy=batch_reorder_policy,
                                cycle_cover_days=batch_cycle_cover_days,
                                min_days_between_orders=batch_min_days_between,
                                moq=batch_moq,
                                casepack=batch_casepack,
                                service_level_z=batch_service_level_z,
                                demand_std_dev=None,
                                use_service_level_safety=batch_use_service_level,
                                stockout_mode=batch_stockout_mode
                            )
                            
                            analytics = analyze_forecast(forecast_df)
                            
                            st.session_state.batch_results.append({
                                'asin': prod['asin'],
                                'params': {
                                    'initial_inventory': int(prod['initial_inventory']),
                                    'sales_velocity': float(velocity),
                                    'lead_time': int(prod['lead_time']),
                                    'safety_stock_days': int(prod['safety_stock_days']),
                                    'start_date': start_date,
                                    'days': batch_forecast_days,
                                    'use_seasonality': batch_use_seasonality,
                                    'dynamic_reorder': batch_dynamic_reorder,
                                    'deliveries': copy.deepcopy(deliveries),
                                    'seasonality_factors': seasonality_copy,
                                    'reorder_policy': batch_reorder_policy,
                                    'cycle_cover_days': batch_cycle_cover_days,
                                    'min_days_between_orders': batch_min_days_between,
                                    'moq': batch_moq,
                                    'casepack': batch_casepack,
                                    'service_level_z': batch_service_level_z,
                                    'demand_std_dev': None,
                                    'use_service_level_safety': batch_use_service_level,
                                    'stockout_mode': batch_stockout_mode
                                },
                                'forecast_df': forecast_df.copy(),
                                'analytics': copy.deepcopy(analytics),
                                'status': 'success'
                            })
                        except Exception as e:
                            st.session_state.batch_results.append({
                                'asin': prod['asin'],
                                'status': 'error',
                                'error': str(e)
                            })
                        
                        processed_count += 1
                        progress_bar.progress(processed_count / len(valid_products))
                    
                    status_text.text("Processing complete!")
                    st.success(f"Processed {len(valid_products)} forecast(s)")
            
            # Display batch results
            if st.session_state.batch_results:
                st.markdown("### Batch Results Summary")
                
                results_data = []
                for result in st.session_state.batch_results:
                    if result['status'] == 'success':
                        analytics = result['analytics']
                        results_data.append({
                            'ASIN': result['asin'],
                            'Status': 'Success',
                            'Stockout Days': analytics.get('stockout_count', 0),
                            'Avg Inventory': f"{analytics.get('avg_inventory', 0):.0f}",
                            'Reorders': analytics.get('reorder_count', 0),
                            'Service Level': f"{analytics.get('service_level', 1.0):.1%}"
                        })
                    else:
                        results_data.append({
                            'ASIN': result['asin'],
                            'Status': f"Error: {result.get('error', 'Unknown')}",
                            'Stockout Days': '-',
                            'Avg Inventory': '-',
                            'Reorders': '-',
                            'Service Level': '-'
                        })
                
                results_df = pd.DataFrame(results_data)
                st.dataframe(results_df, use_container_width=True, hide_index=True)
            
            if save_all and st.session_state.batch_results:
                saved_count = 0
                error_count = 0
                
                for result in st.session_state.batch_results:
                    if result['status'] == 'success':
                        try:
                            forecast_name = f"Batch Forecast - {result['asin']} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                            
                            save_forecast(
                                name=forecast_name,
                                asin=result['asin'],
                                description=f"Batch processed forecast for {result['asin']}",
                                parameters=result['params'],
                                forecast_df=result['forecast_df'],
                                analytics=result['analytics']
                            )
                            saved_count += 1
                        except Exception as e:
                            error_count += 1
                            st.error(f"Error saving {result['asin']}: {str(e)}")
                
                if saved_count > 0:
                    st.success(f"Successfully saved {saved_count} forecast(s) to database!")
                if error_count > 0:
                    st.warning(f"{error_count} forecast(s) failed to save.")
        
        else:
            # Original single product entry mode
            # Show loaded data indicator and quick actions
            if st.session_state.get('loaded_forecast'):
                loaded_forecast = st.session_state.loaded_forecast
                st.info(f"📋 **Parameters loaded from:** {loaded_forecast['name']} - You can modify any values below to override the loaded data.")
                
                # Quick actions for loaded forecast
                with st.expander("💾 Quick Actions for Loaded Forecast"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # ASIN input for loaded forecast
                        current_loaded_asin = loaded_forecast.get('asin', '')
                        quick_asin = st.text_input(
                            "Update ASIN for this session",
                            value=st.session_state.get('current_asin', current_loaded_asin),
                            placeholder="Enter ASIN/SKU (e.g., B01234567X)",
                            help="This will be used when saving the forecast"
                        )
                        if quick_asin != st.session_state.get('current_asin', ''):
                            st.session_state.current_asin = quick_asin
                    
                    with col2:
                        st.write("")  # Spacing
                        st.write("")  # Spacing
                        
                        # Quick save button (only show if we have forecast data)
                        if st.session_state.get('forecast_data') is not None:
                            if st.button("💾 Quick Save Current Forecast", type="primary"):
                                try:
                                    # Use current ASIN or loaded forecast ASIN
                                    save_asin = st.session_state.get('current_asin', '') or current_loaded_asin
                                    
                                    # Generate a name based on current parameters
                                    quick_name = f"Updated Forecast - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                                    
                                    forecast_id = save_forecast(
                                        name=quick_name,
                                        asin=save_asin,
                                        description=f"Updated version based on {loaded_forecast['name']}",
                                        parameters=st.session_state.forecast_params,
                                        forecast_df=st.session_state.forecast_data,
                                        analytics=st.session_state.analytics
                                    )
                                    st.success(f"Forecast saved successfully! ID: {forecast_id}")
                                    if save_asin:
                                        st.info(f"Saved under ASIN: {save_asin}")
                                except Exception as e:
                                    st.error(f"Error saving forecast: {str(e)}")
                        else:
                            st.caption("Run a forecast first to enable quick save")
            
            # Sales velocity input options
            velocity_options = st.radio(
                "Sales Velocity Input Method",
                ["Simple", "Weighted Average (Multiple Time Periods)"],
                index=0 if not st.session_state.use_weighted_velocity else 1,
                horizontal=True
            )
            
            # Update session state based on selection
            st.session_state.use_weighted_velocity = (velocity_options == "Weighted Average (Multiple Time Periods)")
            
            if not st.session_state.use_weighted_velocity:
                # Simple single velocity input
                st.session_state.sales_velocity = st.number_input(
                    "Daily Sales Velocity (units/day)", 
                    min_value=0.1, 
                    value=st.session_state.sales_velocity,
                    step=0.1,
                    format="%.2f"
                )
            else:
                # Weighted velocity calculator
                st.markdown("### Sales Data & Weights")
                st.info("Enter sales data for different time periods and assign weights to calculate a blended sales velocity.")
                
                # Initialize velocities dictionary
                velocities = {}
                periods = get_default_periods()
                
                # Create columns for period sales and weights
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.markdown("**Time Period**")
                with col2:
                    st.markdown("**Sales (units)**")
                with col3:
                    st.markdown("**Weight**")
                
                # Create input rows for each period
                for period in periods:
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.markdown(f"**{format_period_name(period)}**")
                    with col2:
                        sales = st.number_input(
                            f"Sales for {format_period_name(period)}",
                            min_value=0,
                            value=st.session_state.period_sales.get(period, 0),
                            step=1,
                            label_visibility="collapsed",
                            key=f"sales_{period}"
                        )
                        st.session_state.period_sales[period] = sales
                        
                        # Calculate velocity for this period
                        days = get_period_days(period)
                        velocity = calculate_daily_velocity(sales, days)
                        velocities[period] = velocity
                    
                    with col3:
                        weight = st.number_input(
                            f"Weight for {format_period_name(period)}",
                            min_value=0.0,
                            max_value=1.0,
                            value=st.session_state.period_weights.get(period, 0.25),
                            step=0.05,
                            format="%.2f",
                            label_visibility="collapsed",
                            key=f"weight_{period}"
                        )
                        st.session_state.period_weights[period] = weight
                
                # Calculate weighted average velocity
                weighted_velocity = calculate_weighted_velocity(velocities, st.session_state.period_weights)
                
                # Save to session state
                st.session_state.sales_velocity = weighted_velocity
                
                # Display the calculated weighted velocity
                st.markdown("---")
                st.markdown(f"### Blended Daily Velocity: **{weighted_velocity:.2f} units/day**")
                
                # Create a table with all velocity calculations
                data_table = get_period_data_table(st.session_state.period_sales, st.session_state.period_weights)
                st.dataframe(data_table, hide_index=True, use_container_width=True)
                
                # Note about weight normalization
                weight_sum = sum(st.session_state.period_weights.values())
                if abs(weight_sum - 1.0) > 0.01:  # If weights don't sum to approximately 1
                    st.info(f"Note: Weights sum to {weight_sum:.2f}. They will be automatically normalized in the calculation.")
            
            st.session_state.initial_inventory = st.number_input(
                "Initial Inventory (units)", 
                min_value=0, 
                value=st.session_state.initial_inventory,
                step=1
            )
            
            # Delivery schedule controls
            st.subheader("Scheduled Deliveries")
            
            # Get forecast start date for reference
            if 'start_date' not in st.session_state:
                start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                start_date = st.session_state.start_date
            
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            st.info("Select specific calendar dates for deliveries instead of day numbers.")
            
            delivery_count = st.number_input("Number of Scheduled Deliveries", 
                                            min_value=0, 
                                            max_value=10, 
                                            value=len(st.session_state.deliveries))
            
            # Initialize date map if not in session state
            if 'delivery_dates' not in st.session_state:
                st.session_state.delivery_dates = {}
                # Convert existing day-based deliveries to dates if any exist
                for i, (day, qty) in enumerate(st.session_state.deliveries):
                    st.session_state.delivery_dates[i] = start_date + timedelta(days=day)
            
            new_deliveries = []
            for i in range(delivery_count):
                col1, col2 = st.columns(2)
                
                # Default date is either existing date or start_date + 30 days for new entries
                if i not in st.session_state.delivery_dates:
                    default_date = start_date + timedelta(days=30)
                    st.session_state.delivery_dates[i] = default_date
                else:
                    default_date = st.session_state.delivery_dates[i]
                
                with col1:
                    # Date picker for delivery date
                    delivery_date = st.date_input(
                        f"Date of Delivery #{i+1}",
                        value=default_date,
                        min_value=today,
                        key=f"delivery_date_{i}"
                    )
                    # Convert date to datetime at midnight
                    delivery_datetime = datetime.combine(delivery_date, datetime.min.time())
                    # Store in session state
                    st.session_state.delivery_dates[i] = delivery_datetime
                    
                    # Calculate day number from start date for internal calculations
                    day_diff = (delivery_datetime - start_date).days
                    if day_diff < 1:
                        st.warning(f"Delivery #{i+1} date must be after forecast start date. Adjusting to day 1.")
                        day_diff = 1
                        
                    # Show the day number for reference
                    st.caption(f"Day {day_diff} from forecast start")
                    day = day_diff
                    
                with col2:
                    qty = st.number_input(
                        f"Quantity for Delivery #{i+1}", 
                        min_value=1, 
                        value=st.session_state.deliveries[i][1] if i < len(st.session_state.deliveries) else 2500,
                        step=100,
                        key=f"delivery_qty_{i}"
                    )
                new_deliveries.append((day, qty))
            
            # Clean up any unused delivery dates
            keys_to_remove = [k for k in st.session_state.delivery_dates.keys() if k >= delivery_count]
            for k in keys_to_remove:
                del st.session_state.delivery_dates[k]
                
            st.session_state.deliveries = new_deliveries
    
    with asin_tab:
        st.subheader("ASIN/SKU Management")
        st.write("Select an existing ASIN or enter a new one to manage forecasts by product.")
        
        # Show current loaded forecast info if any
        if st.session_state.get('loaded_forecast'):
            loaded_forecast = st.session_state.loaded_forecast
            col1, col2 = st.columns([3, 1])
            with col1:
                st.info(f"📋 **Currently loaded:** {loaded_forecast['name']} (ASIN: {loaded_forecast.get('asin', 'N/A')})")
            with col2:
                if st.button("Clear Loaded Data", type="secondary"):
                    # Clear loaded forecast data
                    st.session_state.loaded_forecast = None
                    st.session_state.forecast_data = None
                    st.session_state.analytics = None
                    st.success("Loaded forecast cleared!")
                    st.rerun()
        
        # Initialize ASIN in session state if not present
        if 'current_asin' not in st.session_state:
            st.session_state.current_asin = ""
        
        # Get unique ASINs from database
        try:
            available_asins = get_unique_asins()
        except Exception as e:
            available_asins = []
            st.error(f"Error loading ASINs: {str(e)}")
        
        # ASIN selection - prioritize existing ASINs
        if available_asins:
            # Primary dropdown for existing ASINs
            asin_options = ["Select existing ASIN..."] + available_asins + ["Enter new ASIN"]
            
            # Determine current index
            current_index = 0
            if st.session_state.current_asin in available_asins:
                current_index = available_asins.index(st.session_state.current_asin) + 1
            elif st.session_state.current_asin and st.session_state.current_asin not in available_asins:
                current_index = len(asin_options) - 1  # "Enter new ASIN"
            
            selected_option = st.selectbox(
                "ASIN/SKU Selection",
                asin_options,
                index=current_index,
                help="Select an existing ASIN to auto-load forecast data, or choose to enter a new one"
            )
            
            if selected_option == "Enter new ASIN":
                # Show text input for new ASIN
                asin_input = st.text_input(
                    "Enter new ASIN/SKU", 
                    value=st.session_state.current_asin if st.session_state.current_asin not in available_asins else "",
                    placeholder="Enter ASIN/SKU (e.g., B01234567X)",
                    help="Enter a new ASIN/SKU for this forecast"
                )
                st.session_state.current_asin = asin_input
            elif selected_option != "Select existing ASIN...":
                # An existing ASIN was selected
                st.session_state.current_asin = selected_option
                asin_input = selected_option
            else:
                # Default state - no selection made yet
                st.session_state.current_asin = ""
                asin_input = ""
        else:
            # No existing ASINs, show only text input
            st.info("No saved ASINs found. Enter a new ASIN below.")
            asin_input = st.text_input(
                "Enter ASIN/SKU", 
                value=st.session_state.current_asin,
                placeholder="Enter ASIN/SKU (e.g., B01234567X)",
                help="Enter an ASIN/SKU for this forecast"
            )
            st.session_state.current_asin = asin_input
        
        # Override ASIN functionality
        if st.session_state.current_asin:
            with st.expander("🎯 Override Current ASIN"):
                st.write("Want to assign this forecast to a different ASIN or start fresh?")
                col1, col2 = st.columns(2)
                with col1:
                    new_asin = st.text_input(
                        "New ASIN/SKU",
                        placeholder="Enter different ASIN (e.g., B09876543Z)",
                        help="This will change the ASIN for the current session"
                    )
                with col2:
                    st.write("")  # Spacing
                    st.write("")  # Spacing
                    if st.button("Apply New ASIN", type="secondary"):
                        if new_asin.strip():
                            st.session_state.current_asin = new_asin.strip()
                            st.success(f"ASIN changed to: {new_asin.strip()}")
                            st.rerun()
                        else:
                            st.error("Please enter a valid ASIN")
        
        # Auto-load functionality when ASIN is entered/selected
        if st.session_state.current_asin and st.session_state.current_asin.strip():
            current_asin = st.session_state.current_asin.strip()
            
            try:
                # Get forecasts for this ASIN
                asin_forecasts = get_forecasts_by_asin(current_asin)
                
                if asin_forecasts:
                    # Show available forecasts for this ASIN
                    st.success(f"Found {len(asin_forecasts)} saved forecast(s) for {current_asin}")
                    
                    # Get the most recent forecast
                    most_recent = asin_forecasts[0]  # Already sorted by created_at desc
                    
                    # Auto-load button or automatic loading
                    auto_load = st.checkbox(
                        f"Auto-load most recent forecast ({most_recent['name']})",
                        value=False,
                        key="auto_load_checkbox"
                    )
                    
                    if auto_load:
                        try:
                            # Load the most recent forecast
                            loaded_data = get_forecast(most_recent['id'])
                            
                            # Update all session state with loaded data
                            params = loaded_data['parameters']
                            
                            # Update core parameters
                            st.session_state.initial_inventory = params['initial_inventory']
                            st.session_state.sales_velocity = params['sales_velocity']
                            st.session_state.lead_time = params['lead_time']
                            st.session_state.safety_stock_days = params['safety_stock_days']
                            st.session_state.deliveries = params['deliveries']
                            st.session_state.seasonality_factors = params['seasonality_factors']
                            
                            # Update weighted velocity parameters if they exist
                            if 'use_weighted_velocity' in params:
                                st.session_state.use_weighted_velocity = params['use_weighted_velocity']
                            if 'period_sales' in params:
                                st.session_state.period_sales = params['period_sales']
                            if 'period_weights' in params:
                                st.session_state.period_weights = params['period_weights']
                            
                            # Store loaded forecast data
                            st.session_state.loaded_forecast = loaded_data
                            st.session_state.forecast_data = loaded_data['forecast_df']
                            st.session_state.analytics = loaded_data['analytics']
                            
                            st.success(f"✅ Loaded forecast: {loaded_data['name']}")
                            st.info(f"Created: {loaded_data['created_at'].strftime('%Y-%m-%d %H:%M')}")
                            st.info("💡 **Tip:** You can now modify any parameters below and run a new forecast. The ASIN field will auto-populate when saving.")
                            
                        except Exception as e:
                            st.error(f"Error loading forecast: {str(e)}")
                    
                    # Show forecast list for this ASIN
                    with st.expander(f"All forecasts for {current_asin} ({len(asin_forecasts)})"):
                        for forecast in asin_forecasts:
                            col_name, col_info, col_load = st.columns([2, 2, 1])
                            with col_name:
                                st.write(f"**{forecast['name']}**")
                            with col_info:
                                st.write(f"Created: {forecast['created_at'].strftime('%Y-%m-%d')}")
                                st.caption(f"Velocity: {forecast['sales_velocity']:.2f}, Days: {forecast['forecast_days']}")
                            with col_load:
                                if st.button(f"Load", key=f"load_{forecast['id']}"):
                                    try:
                                        loaded_data = get_forecast(forecast['id'])
                                        
                                        # Update session state (same as auto-load above)
                                        params = loaded_data['parameters']
                                        st.session_state.initial_inventory = params['initial_inventory']
                                        st.session_state.sales_velocity = params['sales_velocity']
                                        st.session_state.lead_time = params['lead_time']
                                        st.session_state.safety_stock_days = params['safety_stock_days']
                                        st.session_state.deliveries = params['deliveries']
                                        st.session_state.seasonality_factors = params['seasonality_factors']
                                        
                                        if 'use_weighted_velocity' in params:
                                            st.session_state.use_weighted_velocity = params['use_weighted_velocity']
                                        if 'period_sales' in params:
                                            st.session_state.period_sales = params['period_sales']
                                        if 'period_weights' in params:
                                            st.session_state.period_weights = params['period_weights']
                                        
                                        st.session_state.loaded_forecast = loaded_data
                                        st.session_state.forecast_data = loaded_data['forecast_df']
                                        st.session_state.analytics = loaded_data['analytics']
                                        
                                        st.success(f"✅ Loaded: {loaded_data['name']}")
                                        st.info("💡 **Tip:** Parameters loaded! Switch to other tabs to modify them or run a new forecast.")
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"Error loading forecast: {str(e)}")
                else:
                    st.info(f"No saved forecasts found for {current_asin}. Create and save a forecast to enable persistence.")
                    
            except Exception as e:
                st.error(f"Error checking ASIN forecasts: {str(e)}")
    
    # Forecast parameters
    st.header("Forecast Parameters")
    
    st.session_state.lead_time = st.number_input(
        "Lead Time (days)", 
        min_value=1, 
        max_value=180, 
        value=st.session_state.lead_time,
        help="The time it takes from placing an order to receiving the inventory"
    )
    
    st.session_state.safety_stock_days = st.number_input(
        "Safety Stock (days)", 
        min_value=0, 
        max_value=60, 
        value=st.session_state.safety_stock_days,
        help="Buffer inventory expressed in days of sales"
    )
    
    forecast_days = st.number_input(
        "Forecast Horizon (days)", 
        min_value=30, 
        max_value=365, 
        value=180,
        help="Number of days to forecast into the future"
    )
    
    # Advanced options
    with st.expander("Advanced Options"):
        use_seasonality = st.checkbox(
            "Enable Seasonality Adjustments", 
            value=False,
            help="Apply monthly seasonality factors to sales velocity"
        )
        
        if use_seasonality:
            st.info("Seasonality factors by month (1.0 = base velocity)")
            
            # Display editable seasonality factors in 4 columns (3 months per column)
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            
            columns = st.columns(4)
            seasonal_factors = {}
            
            for i, month in enumerate(range(1, 13)):
                col_index = i // 3
                with columns[col_index]:
                    factor = st.number_input(
                        f"{month_names[i]}",
                        min_value=0.1,
                        max_value=5.0,
                        value=float(st.session_state.seasonality_factors.get(month, 1.0)),
                        step=0.1,
                        format="%.1f",
                        key=f"season_{month}"
                    )
                    seasonal_factors[month] = factor
            
            st.session_state.seasonality_factors = seasonal_factors
        
        dynamic_reorder = st.checkbox(
            "Enable Dynamic Reorder Logic", 
            value=True,
            help="Automatically generate reorder recommendations"
        )
        
        # Professional Inventory Management Parameters
        st.markdown("### **Professional Inventory Parameters**")
        st.info("Configure advanced inventory management settings for professional forecasting")
        
        # Reorder Policy Selection
        reorder_policy = st.selectbox(
            "Reorder Policy",
            options=['R_S', 's_Q', 'EOQ'],
            index=0,
            help="R_S = Order-up-to policy, s_Q = Fixed lot size, EOQ = Economic Order Quantity"
        )
        
        # Safety Stock Method
        safety_stock_method = st.radio(
            "Safety Stock Method",
            options=["Days-based (Simple)", "Service Level (Statistical)"],
            index=0,
            horizontal=True,
            help="Choose between simple days-based or statistical service level safety stock"
        )
        
        use_service_level_safety = (safety_stock_method == "Service Level (Statistical)")
        
        col1, col2 = st.columns(2)
        with col1:
            if use_service_level_safety:
                service_level_z = st.number_input(
                    "Service Level Z-Score",
                    min_value=0.5,
                    max_value=3.0,
                    value=1.65,
                    step=0.1,
                    format="%.2f",
                    help="1.65 = ~95% service level, 1.96 = ~97.5%, 2.33 = ~99%"
                )
                
                demand_std_dev_pct = st.number_input(
                    "Demand Variability (%)",
                    min_value=5.0,
                    max_value=100.0,
                    value=20.0,
                    step=5.0,
                    format="%.1f",
                    help="Daily demand standard deviation as % of mean"
                )
                demand_std_dev = st.session_state.sales_velocity * (demand_std_dev_pct / 100)
            else:
                service_level_z = 1.65
                demand_std_dev = None
        
        with col2:
            cycle_cover_days = st.number_input(
                "Cycle Coverage (days)",
                min_value=10,
                max_value=120,
                value=35,
                step=5,
                help="Days of coverage for order-up-to level (was hardcoded at 80)"
            )
            
            min_days_between_orders = st.number_input(
                "Min Days Between Orders",
                min_value=1,
                max_value=90,
                value=30,
                step=5,
                help="Minimum frequency between reorders (was hardcoded at 40)"
            )
        
        # MOQ and Casepack
        col3, col4 = st.columns(2)
        with col3:
            moq = st.number_input(
                "Minimum Order Quantity (MOQ)",
                min_value=0,
                value=0,
                step=100,
                help="Minimum order size required"
            )
        
        with col4:
            casepack = st.number_input(
                "Casepack Multiple",
                min_value=1,
                value=1,
                step=1,
                help="Orders must be in multiples of this number"
            )
        
        # Stockout Mode
        stockout_mode = st.radio(
            "Stockout Handling",
            options=["lost_sales", "backorders"],
            index=0,
            horizontal=True,
            help="lost_sales = demand lost when out of stock, backorders = demand fulfilled when inventory arrives"
        )
        
        start_date_val = st.date_input(
            "Forecast Start Date",
            value=datetime.now().date(),
            help="The first day of the forecast"
        )
        # Store the start date in session state for delivery date calculations
        start_date = datetime.combine(start_date_val, datetime.min.time())
        st.session_state.start_date = start_date

# Main content area
forecast_tab, saved_tab, data_tab, help_tab = st.tabs(["Forecast", "Saved Forecasts", "Data View", "Help"])

# Define a function to display forecast chart from any forecast dataframe
def display_forecast_chart(forecast_df, dynamic_reorder=True, height=500):
    import uuid
    chart_id = str(uuid.uuid4())[:8]  # Short unique ID for this chart instance
    
    fig = go.Figure()
    
    # Add inventory line
    fig.add_trace(go.Scatter(
        x=forecast_df['date'],
        y=forecast_df['inventory'],
        mode='lines',
        name='Inventory',
        line=dict(color='royalblue', width=2),
        uid=f'inventory_{chart_id}'
    ))
    
    # Add safety stock line
    fig.add_trace(go.Scatter(
        x=forecast_df['date'],
        y=forecast_df['safety_stock'],
        mode='lines',
        name='Safety Stock',
        line=dict(color='red', width=1, dash='dash'),
        uid=f'safety_{chart_id}'
    ))
    
    # Add inventory position line if available
    if 'inventory_position' in forecast_df.columns:
        fig.add_trace(go.Scatter(
            x=forecast_df['date'],
            y=forecast_df['inventory_position'],
            mode='lines',
            name='Inventory Position',
            line=dict(color='purple', width=1, dash='dot'),
            uid=f'inventory_position_{chart_id}'
        ))
    
    # Add reorder point line if available
    if 'reorder_point' in forecast_df.columns:
        fig.add_trace(go.Scatter(
            x=forecast_df['date'],
            y=forecast_df['reorder_point'],
            mode='lines',
            name='Reorder Point',
            line=dict(color='orange', width=1, dash='dashdot'),
            uid=f'reorder_point_{chart_id}'
        ))
    
    # Mark delivery days with annotations
    deliveries = forecast_df[forecast_df['delivery'] > 0]
    if not deliveries.empty:
        fig.add_trace(go.Scatter(
            x=deliveries['date'],
            y=deliveries['inventory'],
            mode='markers',
            name='Deliveries',
            marker=dict(color='green', size=10, symbol='triangle-up'),
            text=deliveries['delivery_amount'].apply(lambda x: f"+{x} units"),
            hoverinfo='text+x+y',
            uid=f'deliveries_{chart_id}'
        ))
    
    # Mark reorder points if dynamic reordering is enabled
    if dynamic_reorder:
        reorders = forecast_df[forecast_df['reorder_trigger']]
        if not reorders.empty:
            fig.add_trace(go.Scatter(
                x=reorders['date'],
                y=reorders['inventory'],
                mode='markers',
                name='Reorder Points',
                marker=dict(color='orange', size=8, symbol='star'),
                text=reorders.apply(lambda row: f"Order: {row['reorder_amount']} units<br>Arrives: Day {row['reorder_arrival_day']}", axis=1),
                hoverinfo='text+x+y',
                uid=f'reorders_{chart_id}'
            ))
    
    # Customize layout
    fig.update_layout(
        title='Daily Inventory Forecast',
        xaxis_title='Date',
        yaxis_title='Inventory (units)',
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=height,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    
    return fig

with forecast_tab:
    # Button to run the forecast
    if st.button("Run Forecast Simulation", type="primary"):
        with st.spinner("Running forecast simulation..."):
            # Use the start date from session state
            start_datetime = st.session_state.start_date
            
            # Run the forecast with professional parameters
            forecast_df = run_forecast(
                initial_inventory=st.session_state.initial_inventory,
                base_velocity=st.session_state.sales_velocity,
                start_date=start_datetime,
                days=forecast_days,
                deliveries=st.session_state.deliveries,
                lead_time=st.session_state.lead_time,
                safety_stock_days=st.session_state.safety_stock_days,
                use_seasonality=use_seasonality,
                seasonality_factors=st.session_state.seasonality_factors,
                dynamic_reorder=dynamic_reorder,
                reorder_policy=reorder_policy,
                cycle_cover_days=cycle_cover_days,
                min_days_between_orders=min_days_between_orders,
                moq=moq,
                casepack=casepack,
                service_level_z=service_level_z,
                demand_std_dev=demand_std_dev,
                use_service_level_safety=use_service_level_safety,
                stockout_mode=stockout_mode
            )
            
            # Analyze the forecast results
            analytics = analyze_forecast(forecast_df)
            
            # Store results in session state
            st.session_state.forecast_data = forecast_df
            st.session_state.analytics = analytics
            
            st.success("Forecast completed successfully!")
            
            # Store parameters for saving (including professional parameters)
            st.session_state.forecast_params = {
                'initial_inventory': st.session_state.initial_inventory,
                'sales_velocity': st.session_state.sales_velocity,
                'lead_time': st.session_state.lead_time,
                'safety_stock_days': st.session_state.safety_stock_days,
                'start_date': start_datetime,
                'days': forecast_days,
                'use_seasonality': use_seasonality,
                'dynamic_reorder': dynamic_reorder,
                'deliveries': st.session_state.deliveries,
                'seasonality_factors': st.session_state.seasonality_factors,
                # Professional inventory parameters
                'reorder_policy': reorder_policy,
                'cycle_cover_days': cycle_cover_days,
                'min_days_between_orders': min_days_between_orders,
                'moq': moq,
                'casepack': casepack,
                'service_level_z': service_level_z,
                'demand_std_dev': demand_std_dev,
                'use_service_level_safety': use_service_level_safety,
                'stockout_mode': stockout_mode,
                # Weighted velocity parameters
                'use_weighted_velocity': st.session_state.use_weighted_velocity,
                'period_sales': st.session_state.period_sales,
                'period_weights': st.session_state.period_weights
            }
            
            # Store weighted velocity parameters in analytics
            # This approach prevents serialization issues with custom objects
            analytics['use_weighted_velocity'] = st.session_state.use_weighted_velocity
            analytics['period_sales'] = st.session_state.period_sales
            analytics['period_weights'] = st.session_state.period_weights
    
    # Display forecast results if available
    if st.session_state.forecast_data is not None:
        forecast_df = st.session_state.forecast_data
        analytics = st.session_state.analytics
        
        # Create enhanced metrics row with professional KPIs
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Avg Inventory", f"{analytics['avg_inventory']:.0f} units")
        
        with col2:
            service_level = analytics.get('service_level', 1.0)
            st.metric("Service Level", f"{service_level:.1%}")
        
        with col3:
            if dynamic_reorder:
                st.metric("Reorders", analytics['reorder_count'])
            else:
                st.metric("Deliveries", analytics['delivery_count'])
        
        with col4:
            turns = analytics.get('inventory_turns', 0)
            st.metric("Inventory Turns", f"{turns:.1f}")
        
        with col5:
            if analytics['stockout_count'] > 0:
                st.metric("Stockout Days", analytics['stockout_count'])
            else:
                st.metric("Stock Status", "✓ No Stockouts")
        
        # Create inventory forecast chart
        st.subheader("Inventory Forecast Chart")
        
        # Create and display chart
        fig = display_forecast_chart(forecast_df, dynamic_reorder=dynamic_reorder)
        st.plotly_chart(fig, use_container_width=True, key="main_forecast_chart")
        
        # Display velocities chart if seasonality is enabled
        if use_seasonality:
            st.subheader("Daily Sales Velocity")
            
            vel_fig = go.Figure()
            
            vel_fig.add_trace(go.Scatter(
                x=forecast_df['date'],
                y=forecast_df['velocity'],
                mode='lines',
                name='Daily Velocity',
                line=dict(color='purple', width=2)
            ))
            
            vel_fig.update_layout(
                title='Seasonally Adjusted Sales Velocity',
                xaxis_title='Date',
                yaxis_title='Units per Day',
                height=300,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            
            st.plotly_chart(vel_fig, use_container_width=True, key="velocity_chart")
        
        # Display enhanced professional analytics
        with st.expander("📊 Professional Forecast Analytics"):
            # Create tabs for different metric categories
            perf_tab, inv_tab, ops_tab = st.tabs(["Performance KPIs", "Inventory Metrics", "Operations"])
            
            with perf_tab:
                # Service Level and Performance Metrics
                col1, col2 = st.columns(2)
                with col1:
                    performance_df = pd.DataFrame({
                        'KPI': [
                            'Service Level',
                            'Fill Rate',
                            'Total Lost Sales',
                            'Total Demand',
                            'Inventory Turns',
                            'Days of Supply'
                        ],
                        'Value': [
                            f"{analytics.get('service_level', 1.0):.2%}",
                            f"{analytics.get('fill_rate', 1.0):.2%}",
                            f"{analytics.get('total_lost_sales', 0):.0f} units",
                            f"{analytics.get('total_demand', 0):.0f} units",
                            f"{analytics.get('inventory_turns', 0):.2f}",
                            f"{analytics.get('days_of_supply', 0):.1f} days"
                        ]
                    })
                    st.dataframe(performance_df, use_container_width=True, hide_index=True)
                
                with col2:
                    # Safety Stock Performance
                    safety_df = pd.DataFrame({
                        'Safety Stock KPI': [
                            'Avg Safety Stock',
                            'Days Below Safety Stock',
                            '% Days Below Safety Stock',
                            'Days Below ROP',
                            '% Days Below ROP'
                        ],
                        'Value': [
                            f"{analytics.get('avg_safety_stock', 0):.0f} units",
                            f"{analytics.get('days_below_safety_stock', 0)} days",
                            f"{analytics.get('pct_days_below_safety_stock', 0):.1f}%",
                            f"{analytics.get('days_below_rop', 0)} days",
                            f"{analytics.get('pct_days_below_rop', 0):.1f}%"
                        ]
                    })
                    st.dataframe(safety_df, use_container_width=True, hide_index=True)
            
            with inv_tab:
                # Inventory Level Analytics
                inventory_df = pd.DataFrame({
                    'Inventory Metric': [
                        'Average Inventory',
                        'Minimum Inventory',
                        'Maximum Inventory',
                        'Avg Inventory Position',
                        'Min Inventory Position',
                        'Max Inventory Position',
                        'Avg Reorder Point',
                        'Max Backorders'
                    ],
                    'Value': [
                        f"{analytics['avg_inventory']:.1f} units",
                        f"{analytics['min_inventory']:.0f} units",
                        f"{analytics['max_inventory']:.0f} units",
                        f"{analytics.get('avg_inventory_position', 0):.1f} units",
                        f"{analytics.get('min_inventory_position', 0):.0f} units",
                        f"{analytics.get('max_inventory_position', 0):.0f} units",
                        f"{analytics.get('avg_reorder_point', 0):.0f} units",
                        f"{analytics.get('max_backorders', 0):.0f} units"
                    ]
                })
                st.dataframe(inventory_df, use_container_width=True, hide_index=True)
            
            with ops_tab:
                # Operational Metrics
                col1, col2 = st.columns(2)
                with col1:
                    # Stockout Information
                    stockout_df = pd.DataFrame({
                        'Stockout Metric': [
                            'Total Stockout Days',
                            'Stockout Periods',
                            'Longest Stockout Duration',
                            'First Stockout Day'
                        ],
                        'Value': [
                            f"{analytics['stockout_count']} days",
                            f"{analytics.get('stockout_periods_count', 0)} periods",
                            f"{analytics.get('longest_stockout_period', 0)} days",
                            f"Day {analytics.get('first_stockout_day', 'N/A')}" if analytics.get('first_stockout_day') else "No stockouts"
                        ]
                    })
                    st.dataframe(stockout_df, use_container_width=True, hide_index=True)
                
                with col2:
                    # Logistics and Orders
                    logistics_df = pd.DataFrame({
                        'Operations Metric': [
                            'Total Deliveries',
                            'Total Units Delivered',
                            'Reorder Events',
                            'Total Units Reordered',
                            'Total Backorder Days',
                            'Avg Backorders'
                        ],
                        'Value': [
                            f"{analytics['delivery_count']} deliveries",
                            f"{analytics['total_delivered']:.0f} units",
                            f"{analytics['reorder_count']} events",
                            f"{analytics['total_reordered']:.0f} units",
                            f"{analytics.get('total_backorder_days', 0)} days",
                            f"{analytics.get('avg_backorders', 0):.1f} units"
                        ]
                    })
                    st.dataframe(logistics_df, use_container_width=True, hide_index=True)
        
        # Save forecast section
        st.markdown("---")
        st.subheader("💾 Save Forecast")
        
        # Get forecast name, ASIN, and description
        forecast_name = st.text_input("Forecast Name", value=f"Inventory Forecast - {datetime.now().strftime('%Y-%m-%d')}")
        
        # Auto-populate ASIN if one is currently selected
        default_asin = st.session_state.get('current_asin', '')
        forecast_asin = st.text_input("ASIN", 
                                     value=default_asin,
                                     placeholder="Enter the Amazon Standard Identification Number",
                                     help="Amazon Standard Identification Number for the product")
        forecast_description = st.text_area("Description (optional)", height=100, 
                                          placeholder="Add notes or comments about this forecast scenario...")
        
        # Save button
        if st.button("Save Forecast to Database", type="secondary"):
            try:
                with st.spinner("Saving forecast to database..."):
                    forecast_id = save_forecast(
                        name=forecast_name,
                        asin=forecast_asin,
                        description=forecast_description,
                        parameters=st.session_state.forecast_params,
                        forecast_df=st.session_state.forecast_data,
                        analytics=st.session_state.analytics
                    )
                    st.success(f"Forecast saved successfully! ID: {forecast_id}")
            except Exception as e:
                st.error(f"Error saving forecast: {str(e)}")
    else:
        # Placeholder when no forecast has been run
        st.info("👈 Configure your forecast parameters in the sidebar and click 'Run Forecast Simulation' to see the results here.")

with saved_tab:
    st.subheader("📋 Saved Forecasts")
    
    # Button to refresh saved forecasts
    if st.button("Refresh Saved Forecasts List"):
        st.session_state.loaded_forecast = None
    
    # Try to get all saved forecasts
    try:
        saved_forecasts = get_forecasts()
        
        if not saved_forecasts:
            st.info("No saved forecasts found. Create a new forecast simulation and save it to see it here.")
        else:
            st.write(f"Found {len(saved_forecasts)} saved forecast(s).")
            
            # Display forecasts table
            forecasts_df = pd.DataFrame(saved_forecasts)
            forecasts_df['created_at'] = pd.to_datetime(forecasts_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
            forecasts_df.rename(columns={
                'created_at': 'Created Date',
                'name': 'Forecast Name',
                'asin': 'ASIN',
                'initial_inventory': 'Initial Inventory',
                'sales_velocity': 'Sales Velocity',
                'forecast_days': 'Days'
            }, inplace=True)
            
            display_cols = ['id', 'Forecast Name', 'ASIN', 'Created Date', 'Initial Inventory', 'Sales Velocity', 'Days']
            st.dataframe(forecasts_df[display_cols], use_container_width=True)
            
            # Forecast management section
            st.markdown("### Forecast Management")
            
            # Initialize selected forecasts in session state
            if 'selected_forecasts' not in st.session_state:
                st.session_state.selected_forecasts = []
            
            # Multi-select for deletion using multiselect widget with session state persistence
            with st.expander("🗑️ Delete Forecasts"):
                st.write("Select forecasts to delete:")
                
                # Create options for multiselect
                forecast_options = {
                    f"ID {row['id']}: {row['Forecast Name']} (ASIN: {row['ASIN'] or 'N/A'})": row['id']
                    for _, row in forecasts_df.iterrows()
                }
                
                # Initialize session state for persistent selection
                if 'delete_selection' not in st.session_state:
                    st.session_state.delete_selection = []
                
                # Filter out any stale selections (forecasts that no longer exist)
                valid_options = list(forecast_options.keys())
                current_selection = [s for s in st.session_state.delete_selection if s in valid_options]
                
                selected_labels = st.multiselect(
                    "Select forecasts to delete",
                    options=valid_options,
                    default=current_selection,
                    key="forecast_delete_multiselect",
                    help="Select one or more forecasts for bulk deletion"
                )
                
                # Update session state with current selection
                st.session_state.delete_selection = selected_labels
                
                # Convert labels back to IDs
                selected_for_deletion = [forecast_options[label] for label in selected_labels]
                
                # Show selected count and delete button
                if selected_for_deletion:
                    st.info(f"Selected {len(selected_for_deletion)} forecast(s) for deletion")
                    
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button("Delete Selected Forecasts", type="secondary"):
                            deleted_count = 0
                            errors = []
                            
                            with st.spinner(f"Deleting {len(selected_for_deletion)} forecast(s)..."):
                                for forecast_id in selected_for_deletion:
                                    try:
                                        delete_forecast(forecast_id)
                                        deleted_count += 1
                                        
                                        # Reset loaded forecast if it was one of the deleted ones
                                        if (st.session_state.loaded_forecast and 
                                            st.session_state.loaded_forecast['id'] == forecast_id):
                                            st.session_state.loaded_forecast = None
                                    except Exception as e:
                                        errors.append(f"ID {forecast_id}: {str(e)}")
                            
                            # Show results
                            if deleted_count > 0:
                                st.success(f"Successfully deleted {deleted_count} forecast(s)")
                            
                            if errors:
                                for error in errors:
                                    st.error(f"Failed to delete {error}")
                            
                            # Clear selection and refresh the page
                            st.session_state.delete_selection = []
                            st.rerun()
                    
                    with col2:
                        if st.button("Clear Selection"):
                            st.session_state.delete_selection = []
                            st.rerun()
                else:
                    st.caption("No forecasts selected for deletion")
            
            # Single forecast loading section
            st.markdown("### Load Forecast")
            selected_id = st.selectbox(
                "Select a forecast to view or load",
                options=forecasts_df['id'].tolist(),
                format_func=lambda x: f"ID {x}: {forecasts_df.loc[forecasts_df['id'] == x, 'Forecast Name'].iloc[0]}"
            )
            
            # Action buttons for selected forecast
            col1, col2 = st.columns(2)
            
            with col1:
                # Load selected forecast
                if st.button("Load Selected Forecast"):
                    try:
                        with st.spinner("Loading forecast data..."):
                            forecast_data = get_forecast(selected_id)
                            st.session_state.loaded_forecast = forecast_data
                            st.success(f"Successfully loaded forecast: {forecast_data['name']}")
                    except Exception as e:
                        st.error(f"Error loading forecast: {str(e)}")
            
            with col2:
                # Quick delete single forecast
                if st.button("Delete This Forecast", type="secondary"):
                    try:
                        with st.spinner("Deleting forecast..."):
                            delete_forecast(selected_id)
                            st.success(f"Successfully deleted forecast ID: {selected_id}")
                            # Reset loaded forecast if it was the one deleted
                            if st.session_state.loaded_forecast and st.session_state.loaded_forecast['id'] == selected_id:
                                st.session_state.loaded_forecast = None
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error deleting forecast: {str(e)}")
    
            # Display loaded forecast
            if st.session_state.loaded_forecast:
                forecast = st.session_state.loaded_forecast
                st.markdown("---")
                st.subheader(f"📊 {forecast['name']}")
                
                # Display ASIN if available
                if forecast['asin']:
                    st.markdown(f"**ASIN:** {forecast['asin']}")
                
                if forecast['description']:
                    st.markdown(f"*{forecast['description']}*")
                
                # Display key parameters
                params = forecast['parameters']
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Initial Inventory", f"{params['initial_inventory']} units")
                with col2:
                    st.metric("Sales Velocity", f"{params['sales_velocity']:.2f} units/day")
                with col3:
                    st.metric("Lead Time", f"{params['lead_time']} days")
                with col4:
                    st.metric("Safety Stock", f"{params['safety_stock_days']} days")
                
                # Show chart for the loaded forecast
                forecast_df = forecast['forecast_df']
                analytics = forecast['analytics']
                
                # Create and display chart
                st.subheader("Forecast Chart")
                fig = display_forecast_chart(forecast_df, dynamic_reorder=params['dynamic_reorder'])
                st.plotly_chart(fig, use_container_width=True, key="saved_forecast_chart")
                
                # Display analytics in expandable section
                with st.expander("View Forecast Analytics"):
                    # Create two dataframes for better organization
                    inventory_df = pd.DataFrame({
                        'Metric': [
                            'Average Inventory',
                            'Minimum Inventory',
                            'Maximum Inventory',
                        ],
                        'Value': [
                            f"{analytics['avg_inventory']:.1f} units",
                            f"{analytics['min_inventory']:.0f} units",
                            f"{analytics['max_inventory']:.0f} units",
                        ]
                    })
                    
                    # Create stockout information dataframe
                    stockout_df = pd.DataFrame({
                        'Metric': [
                            'Total Stockout Days',
                            'Stockout Periods',
                            'Longest Stockout Duration',
                        ],
                        'Value': [
                            f"{analytics['stockout_count']} days",
                            f"{analytics.get('stockout_periods_count', 0)} periods",
                            f"{analytics.get('longest_stockout_period', 0)} days" +
                            (f" (starting day {analytics.get('longest_stockout_start')})" if analytics.get('longest_stockout_period', 0) > 0 else "")
                        ]
                    })
                    
                    # Create deliveries and reorders dataframe
                    logistics_df = pd.DataFrame({
                        'Metric': [
                            'Total Deliveries',
                            'Total Units Delivered',
                            'Reorder Events',
                            'Total Units Reordered'
                        ],
                        'Value': [
                            f"{analytics['delivery_count']} deliveries",
                            f"{analytics['total_delivered']:.0f} units",
                            f"{analytics['reorder_count']} events",
                            f"{analytics['total_reordered']:.0f} units"
                        ]
                    })
                    
                    # Combine all dataframes for display
                    analytics_df = pd.concat([inventory_df, stockout_df, logistics_df])
                    st.dataframe(analytics_df, use_container_width=True, hide_index=True)
                
                # Load parameters button
                if st.button("Load Parameters to Current Forecast"):
                    try:
                        # Update session state with parameters from loaded forecast
                        st.session_state.initial_inventory = params['initial_inventory']
                        st.session_state.sales_velocity = params['sales_velocity']
                        st.session_state.lead_time = params['lead_time']
                        st.session_state.safety_stock_days = params['safety_stock_days']
                        st.session_state.deliveries = params['deliveries']
                        st.session_state.seasonality_factors = params['seasonality_factors']
                        
                        # Load weighted velocity information if available
                        if 'use_weighted_velocity' in params:
                            st.session_state.use_weighted_velocity = params['use_weighted_velocity']
                        
                        if 'period_sales' in params:
                            st.session_state.period_sales = params['period_sales']
                            
                        if 'period_weights' in params:
                            st.session_state.period_weights = params['period_weights']
                        
                        # Reset current forecast data
                        st.session_state.forecast_data = None
                        st.session_state.analytics = None
                        st.success("Parameters loaded! Go to the Forecast tab to run a new simulation.")
                    except Exception as e:
                        st.error(f"Error loading parameters: {str(e)}")
    except Exception as e:
        st.error(f"Error accessing saved forecasts: {str(e)}")

with data_tab:
    # Display the forecast data table if available
    if st.session_state.forecast_data is not None:
        st.subheader("Forecast Data Table")
        
        # Format the data for display
        display_df = st.session_state.forecast_data.copy()
        display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
        
        # Add event column
        display_df['event'] = ''
        display_df.loc[display_df['delivery'] > 0, 'event'] = display_df.loc[display_df['delivery'] > 0, 'delivery_amount'].apply(lambda x: f"Delivery: +{x} units")
        display_df.loc[display_df['reorder_trigger'], 'event'] = display_df.loc[display_df['reorder_trigger'], 'reorder_amount'].apply(lambda x: f"Reorder: {x} units")
        display_df.loc[display_df['inventory'] == 0, 'event'] = 'STOCKOUT'
        
        # Select columns to display
        display_columns = ['day', 'date', 'inventory', 'velocity', 'event', 'safety_stock']
        
        # Display the table
        st.dataframe(display_df[display_columns], use_container_width=True)
        
        # Add download button for the data
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="Download Forecast Data",
            data=csv,
            file_name="inventory_forecast.csv",
            mime="text/csv"
        )
    else:
        st.info("Run a forecast to see the data table here.")

with help_tab:
    st.subheader("How to Use This Tool")
    
    st.markdown("""
    ### Quick Start Guide
    
    1. **Input Data**: Either upload a CSV/Excel file with your sales and inventory data or manually enter values in the sidebar.
    
    2. **Configure Parameters**:
       - Set your initial inventory level
       - Choose between simple velocity input or weighted average from multiple time periods
       - Configure scheduled deliveries (day and quantity)
       - Set lead time and safety stock days
       
    3. **Advanced Options**:
       - Enable seasonality to adjust sales velocity by month
       - Toggle dynamic reorder logic to simulate automatic reordering
       
    4. **Run Simulation**: Click the "Run Forecast Simulation" button to generate the forecast.
    
    5. **Analyze Results**: View the interactive chart and data table to understand your inventory projection.
    
    6. **Save and Load Forecasts**: 
       - Save your forecasts to the database for future reference
       - Load saved forecasts to compare different scenarios
       - Copy parameters from saved forecasts to create new simulations
    
    ### Key Concepts
    
    - **Sales Velocity**: The average number of units sold per day.
    - **Weighted Velocity**: A blended daily sales rate that combines multiple time periods (7-day, 30-day, etc.) with different weights.
    - **Lead Time**: The time it takes from placing an order to receiving inventory (typically 80 days).
    - **Safety Stock**: Buffer inventory kept to prevent stockouts, expressed in days of sales.
    - **Seasonality**: Monthly adjustments to the base sales velocity to account for seasonal variations.
    - **Dynamic Reordering**: Automatic reorder recommendations based on projected inventory levels.
    
    ### Using Weighted Sales Velocity
    
    1. In the "Manual Entry" tab, select "Weighted Average (Multiple Time Periods)" option.
    2. Enter sales data for each time period (7-day, 30-day, 60-day, 90-day).
    3. Assign weights to each period (weights are automatically normalized if they don't sum to 1.0).
    4. The system calculates individual daily velocities for each period and then applies the weights.
    5. The resulting blended daily velocity is used for the forecast simulation.
    6. This allows you to give more importance to recent sales trends or balance between short and long-term data.
    
    ### Chart Elements
    
    - **Blue Line**: Projected inventory level over time
    - **Red Dashed Line**: Safety stock threshold
    - **Green Triangles**: Scheduled or recommended deliveries
    - **Orange Stars**: Reorder trigger points (when dynamic reordering is enabled)
    
    ### Common Patterns
    
    - The inventory line slopes downward as products are sold
    - Vertical spikes occur when deliveries arrive
    - If the blue line touches zero, a stockout has occurred
    
    ### Using the Database
    
    - **Save Forecasts**: After running a simulation, you can save it with a name, ASIN, and description
    - **View Saved Forecasts**: Go to the "Saved Forecasts" tab to see all your saved simulations
    - **Track by ASIN**: Associate forecasts with specific products using the Amazon Standard Identification Number
    - **Load a Forecast**: Select any saved forecast to view its results or load its parameters
    - **Compare Scenarios**: Save different forecast scenarios to compare their outcomes
    - **Delete Forecasts**: Remove forecasts you no longer need
    """)

# Footer
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #888;">
    Inventory Forecast Simulator | Based on daily simulation approach with dynamic reordering
    </div>
    """, 
    unsafe_allow_html=True
)
