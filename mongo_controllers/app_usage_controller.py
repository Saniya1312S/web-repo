# mongo_controllers/app_usage_controller.py
import os
from flask import request, Response, jsonify
from flask_restx import Namespace, Resource
from bson import json_util
from childcareconfig import child_db_instance,MongoDB_time_interval, calculate_rolling_intervals
from pendulum import from_timestamp, now, parse

# Initialize a Namespace for app_usage-related API routes
app_usage_namespace = Namespace("app_usage", description="Mobile App Usage Management")

# device_type = "WEB"
collection_type = "app_usage"
db_handle = child_db_instance.childcaredb_connection()

@app_usage_namespace.route('/single_app_usage_insert')
class InsertSingleAppUsageData(Resource):
    @app_usage_namespace.doc(responses={
        201: 'Document inserted successfully',
        400: 'Invalid input data',
        500: 'Insertion failed'
    })
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            # Validate required fields: device_id, time, and app_usage
            if not all(k in data for k in ("device_id", "time", "app_usage", "installed_apps", "uninstalled_apps")):
                return {"message": "Missing required fields in request"}, 400

            app_usage_data = {
                "device_id": data['device_id'],
                "time": data['time'],
                "app_usage": [],
                "installed_apps": [],
                "uninstalled_apps": []
            }

            # Validate and process each app_usage entry
            for usage in data['app_usage']:
                if not all(k in usage for k in ("app_name", "package_name", "usage_time", "sessions")):
                    return {"message": "Invalid app_usage format, missing required fields"}, 400

                sessions = []
                for session in usage['sessions']:
                    if not all(k in session for k in ("start_time", "end_time", "duration")):
                        return {"message": "Invalid session format, missing required fields"}, 400
                    sessions.append(session)

                app_usage_data['app_usage'].append({
                    "app_name": usage['app_name'],
                    "package_name": usage['package_name'],
                    "usage_time": usage['usage_time'],
                    "sessions":sessions
                })

            # Process installed apps
            for installed_app in data['installed_apps']:
                if not all(k in installed_app for k in ("app_name", "package_name", "installed_time")):
                    return {"message": "Invalid installed_apps format, missing required fields"}, 400
                app_usage_data['installed_apps'].append({
                    "app_name": installed_app['app_name'],
                    "package_name": installed_app['package_name'],
                    "installed_time": installed_app['installed_time']
                })

            # Process uninstalled apps
            for uninstalled_app in data['uninstalled_apps']:
                if not all(k in uninstalled_app for k in ("app_name", "package_name", "uninstalled_time")):
                    return {"message": "Invalid uninstalled_apps format, missing required fields"}, 400
                app_usage_data['uninstalled_apps'].append({
                    "app_name": uninstalled_app['app_name'],
                    "package_name": uninstalled_app['package_name'],
                    "uninstalled_time": uninstalled_app['uninstalled_time']
                })

            # Insert the document into the database (use the 'app_usage' collection)
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_id = child_db_instance.insert_one_document(collection_name, app_usage_data)
            if inserted_id:
                return {"message": "Document inserted successfully", "inserted_id": str(inserted_id)}, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            return {"message": str(e)}, 500

# Route for inserting multiple app usage data documents
@app_usage_namespace.route('/multiple_app_usage_insert')
class InsertMultipleAppUsageData(Resource):
    @app_usage_namespace.doc(responses={
        201: 'Documents inserted successfully',
        400: 'Invalid input data',
        500: 'Insertion failed'
     })
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            if not isinstance(data, list):
                return {"message": "Data should be a list of documents"}, 400

            app_usage_data_list = []
            for item in data:
                # Validate required fields for each document
                if not all(k in item for k in ("device_id", "time", "app_usage", "installed_apps", "uninstalled_apps")):
                    return {"message": "Missing required fields in one of the documents"}, 400

                app_usage_data = {
                    "device_id": item['device_id'],
                    "time": item['time'],
                    "app_usage": [],
                    "installed_apps": [],
                    "uninstalled_apps": []
                }

                # Validate and process each app_usage entry
                for usage in item['app_usage']:
                    if not all(k in usage for k in ("app_name", "package_name", "usage_time", "sessions")):
                        return {"message": "Invalid app_usage format, missing required fields"}, 400

                    sessions = []
                    for session in usage['sessions']:
                        if not all(k in session for k in ("start_time", "end_time", "duration")):
                            return {"message": "Invalid session format, missing required fields"}, 400
                        sessions.append(session)

                    app_usage_data['app_usage'].append({
                        "app_name": usage['app_name'],
                        "package_name": usage['package_name'],
                        "usage_time": usage['usage_time'],
                        "sessions":  sessions
                    })

                # Process installed apps
                for installed_app in item['installed_apps']:
                    if not all(k in installed_app for k in ("app_name", "package_name", "installed_time")):
                        return {"message": "Invalid installed_apps format, missing required fields"}, 400
                    app_usage_data['installed_apps'].append({
                        "app_name": installed_app['app_name'],
                        "package_name": installed_app['package_name'],
                        "installed_time": installed_app['installed_time']
                    })

                # Process uninstalled apps
                for uninstalled_app in item['uninstalled_apps']:
                    if not all(k in uninstalled_app for k in ("app_name", "package_name", "uninstalled_time")):
                        return {"message": "Invalid uninstalled_apps format, missing required fields"}, 400
                    app_usage_data['uninstalled_apps'].append({
                        "app_name": uninstalled_app['app_name'],
                        "package_name": uninstalled_app['package_name'],
                        "uninstalled_time": uninstalled_app['uninstalled_time']
                    })

                app_usage_data_list.append(app_usage_data)

            # Insert the documents into the database (use the 'app_usage' collection)
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            inserted_ids = child_db_instance.insert_multiple_documents(collection_name, app_usage_data_list)
            if inserted_ids:
                return {
                    "message": "Documents inserted successfully",
                    "inserted_ids": [str(_id) for _id in inserted_ids]
                }, 201
            else:
                return {"message": "Insertion failed"}, 500

        except Exception as e:
            return {"message": str(e)}, 500


# Route for retrieving filtered call data using a static timestamp
@app_usage_namespace.route('/get_app_usage_filter_data')
class GetAppUsageFilterData(Resource):
    @app_usage_namespace.doc(responses={
        200: 'Returns filtered app usage data',
        400: 'device_id query parameter is required',
        404: 'No matching data found using filter',
        500: 'Error creating filter'
    })
    @app_usage_namespace.param('device_id', 'Device ID to fetch app usage data for', type=str)
    def get(self):
        device_id = request.args.get("device_id")
        if not device_id:
            return {"message": "device_id query parameter is required"}, 400

        # Use the static time "2025-01-31T18:30:00.000" (adjusted as needed)
        static_time = parse("2025-01-31T18:30:00.000")

        try:
            collection_name, _ = child_db_instance.device_db_collection(collection_type)
            
            # Convert MongoDB_time_interval to float to avoid type errors.
            interval = float(child_db_instance.MongoDB_time_interval)
            # Call the calulate_rolling_intervals function with the static time
            rolling_filter = calculate_rolling_intervals(device_id, static_time, interval)
            if not rolling_filter:
                return {"message": "Error creating filter"}, 500

            # Execute the aggregation pipeline using aggregate()
            result_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)
            result = list(result_cursor)
            if result:
                app_usage_data = result[0].get("app_usage", [])
                return Response(json_util.dumps(app_usage_data), content_type="application/json", status=200)
            else:
                return {"message": "No matching data found using filter"}, 404

        except Exception as e:
            return {"message": str(e)}, 500



# Define an API endpoint to fetch call-related data
@app_usage_namespace.route('/get_app_usage_data')
class GetAppUsageData(Resource):
    @app_usage_namespace.doc(responses={
        200: 'Returns app usage data for the specified device_id',
        400: 'device_id is required',
        404: 'No app usage data found for the given device_id',
        500: 'Error fetching app usage data'
    })
    @app_usage_namespace.param('device_id', 'Device ID to fetch app usage data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')  # Retrieve device_id from query parameters
        if not device_id:
            return {"message": "device_id is required"}, 400
        
        # Fetch the call data from the MongoDB collection
        collection_name = child_db_instance.device_db_collection(collection_type)[0]  # Assuming 'call' is the collection type
        try:
            data = child_db_instance.get_device_data(collection_name, device_id)
            if data:
                # Convert the MongoDB cursor to a list and then to JSON
                return Response(json_util.dumps(data), content_type='application/json')
            else:
                return {"message": "No call data found for the given device_id"}, 404
        except Exception as e:
            return {"message": f"Error fetching call data: {str(e)}"}, 500

# Helper method to handle pagination for Current, Previous, and Next
def get_paginated_data(app_data_type, device_id, page, per_page, pagination_type):
    try:
        # Convert the static reference time to Pendulum DateTime
        static_time = from_timestamp(1738367999)  # static 'end_time'
        
        # Fetch MongoDB_time_interval, set to 1 day if not available
        try:
            interval_days = float(os.getenv("MongoDB_time_interval", 1))
        except Exception as e:
            return {"message": "MongoDB_time_interval is not set or invalid"}, 500
        
        # Handle different pagination types: previous, current, or next
        if pagination_type == 'previous':
            start_time = static_time.subtract(days=interval_days * 2)
        elif pagination_type == 'next':
            start_time = static_time.add(days=interval_days * 2)
        else:
            # For current pagination, just use the calculated start_time
            start_time = static_time.subtract(days=interval_days)

        # Build your aggregation query with the start_time
        rolling_filter = calculate_rolling_intervals(device_id, start_time, interval_days)
        if not rolling_filter:
            return {"message": "Error creating filter"}, 500

        # Execute the aggregation pipeline (MongoDB query)
        collection_name = child_db_instance.device_db_collection(collection_type)[0]
        result_cursor = child_db_instance._childcaredb_handle[collection_name].aggregate(rolling_filter)

        # Flatten the results
        all_app_usage = []
        all_installed_apps = []
        all_uninstalled_apps = []

        for doc in result_cursor:
            if 'app_usage' in doc:
                all_app_usage.extend(doc['app_usage'])
            if 'installed_apps' in doc:
                all_installed_apps.extend(doc['installed_apps'])
            if 'uninstalled_apps' in doc:
                all_uninstalled_apps.extend(doc['uninstalled_apps'])

        # Select the dataset based on app_data_type
        if app_data_type == 'app_usage':
            data_to_return = all_app_usage
        elif app_data_type == 'installed_apps':
            data_to_return = all_installed_apps
        elif app_data_type == 'uninstalled_apps':
            data_to_return = all_uninstalled_apps
        else:
            return {"message": "Invalid app_data_type specified"}, 400

        # Pagination logic
        total_count = len(data_to_return)
        total_pages = (total_count + per_page - 1) // per_page
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        paginated_data = data_to_return[start_index:end_index]

        if paginated_data:
            response = {
                "data": json_util.dumps(paginated_data),
                "total_count": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
            return Response(response['data'], content_type="application/json")
        else:
            # Return a 200 OK with a message if no data is found
            return {
                "message": f"No data found for the date {start_time.format('YYYY-MM-DD')}. Try checking for a different date."
            }, 200  # HTTP 200 OK for no data found, but valid request

    except Exception as e:
        print(f"Error fetching paginated data: {str(e)}")
        return {"message": "Internal Server Error"}, 500







# API Endpoints for current, next, and previous pagination with the specified parameters

@app_usage_namespace.route('/get_paginated_app_usage_data')
class GetPaginatedCurrentAppUsageData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch app usage data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('app_usage', device_id, page, per_page, 'current')


@app_usage_namespace.route('/get_paginated_previous_app_usage_data')
class GetPaginatedPreviousAppUsageData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch app usage data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('app_usage', device_id, page, per_page, 'previous')


@app_usage_namespace.route('/get_paginated_next_app_usage_data')
class GetPaginatedNextAppUsageData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch app usage data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('app_usage', device_id, page, per_page, 'next')


@app_usage_namespace.route('/get_paginated_installed_apps_data')
class GetPaginatedCurrentInstalledAppsData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch installed apps data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('installed_apps', device_id, page, per_page, 'current')


@app_usage_namespace.route('/get_paginated_previous_installed_apps_data')
class GetPaginatedPreviousInstalledAppsData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch installed apps data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('installed_apps', device_id, page, per_page, 'previous')


@app_usage_namespace.route('/get_paginated_next_installed_apps_data')
class GetPaginatedNextInstalledAppsData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch installed apps data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('installed_apps', device_id, page, per_page, 'next')


@app_usage_namespace.route('/get_paginated_uninstalled_apps_data')
class GetPaginatedCurrentUninstalledAppsData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch uninstalled apps data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('uninstalled_apps', device_id, page, per_page, 'current')


@app_usage_namespace.route('/get_paginated_previous_uninstalled_apps_data')
class GetPaginatedPreviousUninstalledAppsData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch uninstalled apps data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('uninstalled_apps', device_id, page, per_page, 'previous')


@app_usage_namespace.route('/get_paginated_next_uninstalled_apps_data')
class GetPaginatedNextUninstalledAppsData(Resource):
    @app_usage_namespace.param('page', 'Page number for pagination', type=int, default=1)
    @app_usage_namespace.param('per_page', 'Number of items per page', type=int, default=5)
    @app_usage_namespace.param('device_id', 'Device ID to fetch uninstalled apps data for', type=str)
    def get(self):
        device_id = request.args.get('device_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 5, type=int)
        return get_paginated_data('uninstalled_apps', device_id, page, per_page, 'next')






