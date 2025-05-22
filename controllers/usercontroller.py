#controllers.usercontroller.py 
from collections import defaultdict
import re
import string
import uuid
from flask_restx import Resource, Namespace
from flask import json, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt, jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import bcrypt
from dbmodels.mobileusermodels import Users, Subscriptions, Plan, Payment, DiscountOffer
from extensions import db
from apimodels.mobileuserapimodel import GuestUserModel, SubscriptionUserModel, login_model, NewMonitoredByModel
import time
import secrets
import string
from dbmodels.mobileusermodels import UserMask 
from childcareconfig import child_db_instance , db_handle 
from bson import ObjectId
from uuid import uuid4

# Initialize userauth_namespace
userauth_namespace = Namespace("user", description="User authentication operations")

# Register models with userauth_namespace
userauth_namespace.models[GuestUserModel.__name__] = GuestUserModel
userauth_namespace.models[SubscriptionUserModel.__name__] = SubscriptionUserModel
userauth_namespace.models[login_model.name] = login_model

def generate_user_id():
    return str(uuid.uuid4())

def hashpassword(user_password):
    password_bytes = user_password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed_password = bcrypt.hashpw(password_bytes, salt)
    return hashed_password.decode('utf-8')

def verify_password(user_password, hashed_password):
    return bcrypt.checkpw(user_password.encode('utf-8'), hashed_password.encode('utf-8'))

def generate_jwt_access_token(user_id, expiration_minutes=30):
    expires = timedelta(minutes=expiration_minutes)

    # If user_id is a dictionary (for complex identity), convert to string
    if isinstance(user_id, dict):
        user_id = json.dumps(user_id)

    token = create_access_token(identity=user_id, expires_delta=expires)
    return token


def generate_jwt_refresh_token(user_id, expiration_minutes=30):
    expires = timedelta(minutes=expiration_minutes) 
    token = create_refresh_token(identity=user_id, expires_delta=expires)
    return token
  
def tokenize_pii(user_name, value):
    
    stripped_value = ''.join(c for c in value if c.isdigit())

    if stripped_value:
        token = ''.join(secrets.choice(string.digits) for _ in range(12))
    else:
        token = ''.join(secrets.choice(string.ascii_letters) for _ in range(12))

    # Save new token mapping to the database
    token_mapping = UserMask(user_name=user_name, Tokenid=token, Tokenvalue=value)
    db.session.add(token_mapping)
    db.session.commit()

    return token

# Function to detokenize (unmask) PII
def detokenize_pii(Tokenid):
    """Detokenize a value from the token."""
    # Look for the Tokenid in the usermask table to get the Tokenvalue (original data)
    token_mapping = UserMask.get_value_for_token(Tokenid) 
    if token_mapping:
        return token_mapping.Tokenvalue  
    return None  # Return None if Tokenid is not found

def calculate_age(date_of_birth):
    try:
        birth_date = datetime.strptime(date_of_birth, "%Y-%m-%d")
    except ValueError:
        try:
            birth_date = datetime.strptime(date_of_birth, "%d-%m-%Y")
        except Exception:
            return 0
    today = datetime.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

def get_plan_details(plan_id):
    plan = Plan.query.filter_by(plan_id=plan_id).first()
    if not plan:
        return None
    return {
        "plan_id": plan.plan_id,
        "duration_days": plan.duration,
        "plan_description": plan.description,
        "amount": float(plan.charges)
    }

def apply_discount(plan_id, discount_code, base_amount):
    current_time = int(time.time())

    discount = DiscountOffer.query.filter_by(
        discount_code=discount_code,
        plan_id=plan_id,
        status=True
    ).first()

    if discount and discount.start_date <= current_time <= discount.end_date:
        try:
            # Try to apply percentage if provided
            if discount.discount_pct:
                percentage_discount = float(discount.discount_pct)
                discounted_amount = base_amount * (percentage_discount / 100)
                final_amount = max(0.0, base_amount - discounted_amount)
            elif discount.discount_amount:
                amount_discount = float(discount.discount_amount)
                final_amount = max(0.0, base_amount - amount_discount)
            else:
                final_amount = base_amount  # No valid discount value found

            return round(final_amount, 2), discount.discount_id
        except (ValueError, TypeError) as e:
            print(f"Discount processing error: {e}")
            return base_amount, None

    return base_amount, None





#api1
#Guest_registration        
       
@userauth_namespace.route("/register")
class UserRegister(Resource):
    @userauth_namespace.expect(GuestUserModel, validate=True)
    @userauth_namespace.doc(responses={
        201: "User created successfully",
        400: "Missing mandatory fields",
        409: "Email already exists",
        500: "Internal Server Error"
    })
    def post(self):
        data = request.get_json()
       
        required_fields = ['USER_NAME', 'USER_PASSWORD', 'COUNTRY_CODE']
        missing_fields = [field for field in required_fields if not data.get(field)]
       
        if missing_fields:
            return {"Message": f"Missing mandatory fields: {', '.join(missing_fields)}"}, 400
       
        email = data['USER_NAME']
 
        # Check if the email already exists in the database
        if Users.get_user_by_email(email):
            return {"Message": "Email already exists"}, 409
 
        # Generate a unique user ID
        user_id = generate_user_id()
        current_timestamp = int(time.time())

        new_user = Users(
            ACTIVE=True,
            USER_ID=user_id,
            USER_NAME=email,  # Use email as USER_NAME
            USER_PASSWORD=hashpassword(data['USER_PASSWORD']),
            USER_ROLES="GUEST",  # Automatically set the role to 'GUEST'
            CREATED_BY=email,
            CREATED_AT=current_timestamp,
            COUNTRY_CODE=data['COUNTRY_CODE']
        )

        # Generate JWT token valid for 14 days
        new_user.USER_TOKEN = generate_jwt_access_token(
            user_id=user_id,
            expiration_minutes=14 * 24 * 60  # 14 days = 20160 minutes
        )
        new_user.USER_TOKEN_EXPIRY_DATE = current_timestamp + (14 * 24 * 60 * 60)

        try:
            new_user.save()
            return {
                "Message": "User created successfully",
                "USER_ID": new_user.USER_ID,
                "USER_TOKEN": new_user.USER_TOKEN,
                "TOKEN_EXPIRY": new_user.USER_TOKEN_EXPIRY_DATE
            }, 201
        except Exception as e:
            db.session.rollback()
            return {"Message": "An error occurred while creating the user", "Error": str(e)}, 500


#api2
# User  
#primary user registration
@userauth_namespace.route("/subscribe")
class FamilyRegisterMySQL(Resource):
    @jwt_required()
    def post(self):
        try:
            user_id = get_jwt_identity()
            if not user_id:
                return {"Message": "Invalid token or missing user ID."}, 401

            data = request.get_json()
            if not data:
                return {"Message": "No data provided."}, 400

            required_fields = [
                'USER_FULL_NAME', 'AADHAR_DETAILS', 'DATE_OF_BIRTH', 'PHONE_NUMBER', 
                'PAYMENT_TYPE','DURATION', 'TRANSACTION_ID', 'CURRENCY', 'AUTO_RENEWAL_FLAG'
            ]
            missing_fields = [
                field for field in required_fields
                if field not in data or (field != "AUTO_RENEWAL_FLAG" and not data[field])
            ]

            if missing_fields:
                return {"Message": f"Missing fields: {', '.join(missing_fields)}"}, 400

            user = Users.get_user_by_user_id(user_id)
            if not user:
                return {"Message": "User not found."}, 404

            phone = data['PHONE_NUMBER']
            existing_user = Users.get_user_by_phone(phone)
            if existing_user and existing_user.USER_ID != user.USER_ID:
                return {"Message": f"Phone number {phone} already exists."}, 409

            current_timestamp = int(time.time())
            plan_type = data.get('PLAN_TYPE')
            duration = data.get('DURATION')

            if not plan_type or not duration:
                return {"Message": "Missing PLAN_TYPE or DURATION"}, 400

            plan_obj = Plan.query.filter_by(plan_type=plan_type, duration=int(duration)).first()

            if not plan_obj:
                return {"Message": f"No plan found for type: {plan_type} and duration: {duration} days"}, 404

            plan_id = plan_obj.plan_id
            plan = {
                "plan_id": plan_obj.plan_id,
                "duration_days": plan_obj.duration,
                "plan_description": plan_obj.description,
                "amount": float(plan_obj.charges)
            }


            if not plan:
                return {"Message": f"Invalid PLAN_ID: {plan_id}"}, 400
            
            existing_txn = Payment.query.filter_by(transaction_id=data['TRANSACTION_ID']).first()
            if existing_txn:
                return {"Message": f"Transaction ID '{data['TRANSACTION_ID']}' already exists."}, 409


            # Apply discount if provided
            discount_code = data.get("DISCOUNT_CODE")
            discount_id = None
            base_amount = plan['amount']
            final_amount = base_amount  # Default to base amount

            if discount_code:
                discounted_amount, discount_id = apply_discount(plan_id, discount_code, base_amount)

                if discount_id is not None and discounted_amount > 0:
                    final_amount = discounted_amount


            duration_days = plan['duration_days']
            # subscription_type = {
            #     30: "monthly",
            #     90: "quarterly",
            #     180: "half-yearly",
            #     365: "yearly"
            # }.get(duration_days, f"{duration_days}-days")
            

            start_date = current_timestamp
            end_date = current_timestamp + (duration_days * 24 * 60 * 60)  # Convert days to seconds
            renewal_date = end_date + 1
            payment_id = str(uuid.uuid4())

            # Update user details
            user.USER_FULL_NAME = data['USER_FULL_NAME']
            user.USER_ROLES = "MASTER"
            user.AADHAR_DETAILS = tokenize_pii(user.USER_NAME, data['AADHAR_DETAILS'])
            user.DATE_OF_BIRTH = tokenize_pii(user.USER_NAME, data['DATE_OF_BIRTH'])
            user.PHONE_NUMBER = phone
            user.FAMILY_ID = phone
            user.UPDATED_AT = current_timestamp
            user.UPDATED_BY = user.USER_NAME

            new_token = generate_jwt_access_token({
                "user_id": user.USER_ID,
                "family_id": user.PHONE_NUMBER,
                "user_roles": user.USER_ROLES
            }, expiration_minutes=int((end_date - current_timestamp) / 60))

            user.USER_TOKEN = new_token
            user.USER_TOKEN_EXPIRY_DATE = end_date
            user.save()


            subscription_id = str(uuid.uuid4())
            subscription = Subscriptions(
                id=subscription_id,
                user_id=user.USER_ID,
                plan_id=plan_id,
                subscription_status="active",
                start_date=start_date,
                end_date=end_date,
                renewal_date=renewal_date,
                subscription_type=duration_days,
                payment_type=data['PAYMENT_TYPE'],
                payment_id=payment_id,
                amount=final_amount,
                currency=data['CURRENCY'],
                auto_renewal_flag=bool(data.get('AUTO_RENEWAL_FLAG', False)),
                discount_id=discount_id,
                created_at=current_timestamp
            )

            db.session.add(subscription)
            
            # Add payment record

            payment = Payment(
                payment_id=payment_id,
                user_id=user.USER_ID,
                amount=final_amount,
                payment_status="success",  # You can handle gateway results dynamically
                transaction_id=data['TRANSACTION_ID'],
                payment_date=current_timestamp,
                payment_type=data['PAYMENT_TYPE']
            )
            db.session.add(payment)

            db.session.commit()

            return {
                "Message": "Subscription successful.",
                "USER_TOKEN": new_token,
                "SUBSCRIPTION_ID": subscription_id,
                "PAYMENT_ID": payment_id,
                "PLAN": plan['plan_description'],
                "DURATION_DAYS": duration_days,
                "AMOUNT_BEFORE_DISCOUNT": base_amount,
                "DISCOUNT_APPLIED": bool(discount_code and discount_id),
                "DISCOUNT_ID": discount_id,
                "FINAL_AMOUNT": final_amount,
                "START_DATE": start_date,
                "END_DATE": end_date
            }, 201


        except Exception as e:
            db.session.rollback()
            return {"Message": "MySQL update failed.", "Error": str(e)}, 500
  

#api3         
@userauth_namespace.route("/guardian-register")
class GuardianRegister(Resource):
    @jwt_required()
    def post(self):
        try:
            identity = get_jwt_identity()
            identity_data = json.loads(identity)
            user_id = identity_data.get("user_id")
            primary_user= user_id

            # Fetch primary user to get their USER_NAME
            primary_user = Users.get_user_by_user_id(user_id)
            if not primary_user:
                return {"Message": "Primary user not found."}, 404

            data = request.get_json()
            if not data:
                return {"Message": "No data provided."}, 400

            required_fields = ['USER_NAME', 'USER_PASSWORD', 'COUNTRY_CODE']
            missing_fields = [field for field in required_fields if not data.get(field)]
            if missing_fields:
                return {"Message": f"Missing fields: {', '.join(missing_fields)}"}, 400

            email = data['USER_NAME']
            if Users.get_user_by_email(email):
                return {"Message": "Email already exists"}, 409

            new_user_id = generate_user_id()
            current_timestamp = int(time.time())

            # Create the new user with "GUEST" role
            new_user = Users(
                ACTIVE=True,
                USER_ID=new_user_id,
                USER_NAME=email,
                USER_PASSWORD=hashpassword(data['USER_PASSWORD']),
                USER_ROLES="GUEST",  # Ensure the role is set to "GUEST"
                CREATED_BY=primary_user.USER_NAME,  # Set to primary user's name
                CREATED_AT=current_timestamp,
                COUNTRY_CODE=data['COUNTRY_CODE']
            )

            # Generate a JWT token for this new user with the family_id included
            new_user.USER_TOKEN = generate_jwt_access_token(
                user_id=new_user_id,
                expiration_minutes=14 * 24 * 60  # 14 days = 20160 minutes
            )

            new_user.USER_TOKEN_EXPIRY_DATE = current_timestamp + (14 * 24 * 60 * 60)

            # Save the user in the database
            new_user.save()

            return {
                "Message": "Guardian (GUEST) user created successfully.",
                "USER_ID": new_user.USER_ID,
                "USER_TOKEN": new_user.USER_TOKEN
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"Message": "Guardian registration failed.", "Error": str(e)}, 500


#api4
#add Guadrian Registration
@userauth_namespace.route("/add_guardian_details")
class AddGuardianDetails(Resource):
    @jwt_required()
    def post(self):
        try:
            # Get identity of primary user from token
            identity = get_jwt_identity()
            identity_data = json.loads(identity)
            primary_user_id = identity_data.get("user_id")
            family_id = identity_data.get("family_id")

            # Validate token data
            if not primary_user_id:
                return {"Message": "Missing user ID in token."}, 401

            # Fetch primary user info for FAMILY_ID and USER_NAME
            primary_user = Users.get_user_by_user_id(primary_user_id)
            if not primary_user:
                return {"Message": "Primary user not found."}, 404

            # Get request data
            data = request.get_json()
            if not data:
                return {"Message": "No data provided."}, 400

            # Required fields from client input
            required_fields = [
                'USER_ID', 'USER_FULL_NAME', 'AADHAR_DETAILS', 'DATE_OF_BIRTH', 'PHONE_NUMBER'
            ]
            missing_fields = [field for field in required_fields if not data.get(field)]
            if missing_fields:
                return {"Message": f"Missing fields: {', '.join(missing_fields)}"}, 400

            # Fetch guardian user by USER_ID
            guardian = Users.get_user_by_user_id(data['USER_ID'])
            if not guardian:
                return {"Message": "Guardian user not found."}, 404

            # Check for phone number conflict
            phone = data['PHONE_NUMBER']
            existing_user = Users.get_user_by_phone(phone)
            if existing_user and existing_user.USER_ID != guardian.USER_ID:
                return {"Message": f"Phone number {phone} already exists."}, 409

            # Update guardian fields from input
            current_timestamp = int(time.time())
            guardian.USER_FULL_NAME = data['USER_FULL_NAME']
            guardian.USER_ROLES = "GAURDIAN"
            guardian.AADHAR_DETAILS = tokenize_pii(guardian.USER_NAME, data['AADHAR_DETAILS'])
            guardian.DATE_OF_BIRTH = tokenize_pii(guardian.USER_NAME, data['DATE_OF_BIRTH'])
            guardian.PHONE_NUMBER = phone

            # Update from primary user
            guardian.FAMILY_ID = family_id
            guardian.UPDATED_BY = guardian.USER_NAME
            guardian.UPDATED_AT = current_timestamp

            # Refresh guardian token
            guardian.USER_TOKEN = generate_jwt_access_token(
                {
                    "user_id": guardian.USER_ID,
                    "family_id": guardian.FAMILY_ID,
                    "user_roles": guardian.USER_ROLES
                },
                expiration_minutes=30 * 24 * 60  # 14 days
            )
            guardian.USER_TOKEN_EXPIRY_DATE = current_timestamp + (30 * 24 * 60 * 60)

            guardian.save()

            return {
                "Message": "Guardian details updated successfully.",
                "USER_TOKEN": guardian.USER_TOKEN
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"Message": "Failed to update guardian details.", "Error": str(e)}, 500

#api5
@userauth_namespace.route("/guardian-family-tree")
class ParentMongoRegister(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"Message": "No input data provided."}, 400

            # Get values from JWT token
            identity = get_jwt_identity()
            identity_data = json.loads(identity)
            family_id = identity_data.get("family_id")
            user_id = identity_data.get("user_id")

            if not family_id or not user_id:
                return {"Message": "Missing family_id or user_id in token."}, 400

            # Validate required fields
            required_fields = ["name", "familyrole", "dob", "address", "mobile", "track"]
            missing_fields = [
                f for f in required_fields
                if f not in data or (f != "track" and not data[f])
            ]

            # Ensure 'track' is a boolean
            if "track" not in data or not isinstance(data["track"], bool):
                missing_fields.append("track")

            if missing_fields:
                return {"Message": f"Missing fields: {', '.join(missing_fields)}"}, 400
            
            # Get creator email from MySQL using user_id
            primary_user = Users.query.filter_by(USER_ID=user_id).first()
            if not primary_user:
                return {"Message": "User not found in MySQL."}, 404

            created_by_email = primary_user.USER_NAME
            current_timestamp = int(time.time())

            member_doc = {
                "member_id": "",
                "user_id":user_id,
                "familyrole": data["familyrole"].lower(),
                "name": data["name"],
                "age": calculate_age(data["dob"]),
                "mobile": data["mobile"],
                # "occupation": data["occupation"],
                "address": data["address"],
                "track": data.get("track")
            }

            collection_name, _ = child_db_instance.device_db_collection("family")
            family_doc = child_db_instance.find_one_document(collection_name, {"family_id": family_id})

            if family_doc:
                # Update existing document
                members = family_doc.get("members", [])
                monitoredby = family_doc["family"].get("monitoredby", [])

                # Check for duplicate by name
                if any(m.get("name", "").lower() == data["name"].lower() for m in members):
                    return {"Message": f"Member '{data['name']}' already exists."}, 409
                
                if any(m.get("mobile", "") == data["mobile"] for m in members):
                    return {"Message": f"Mobile number '{data['mobile']}' already exists."}, 409

                member_doc["member_id"] = f"{family_id}-{str(len(members)+1).zfill(2)}"
                members.append(member_doc)

                if data["name"] not in monitoredby:
                    monitoredby.append(data["name"])

                update_data = {
                    "$set": {
                        "members": members,
                        "family.monitoredby": monitoredby,
                        "updated_by": created_by_email,
                        "updated_at": current_timestamp
                    }
                }

                child_db_instance.update_one_document(collection_name, {"family_id": family_id}, update_data)

                return {
                    "Message": "Parent added to existing family."
                }, 201

            else:
                # Create new document
                member_doc["member_id"] = f"{family_id}-01"
                monitoredby = [data["name"]]

                new_family_doc = {
                    "_id": ObjectId(),
                    "active": True,
                    "family_id": family_id,
                    "created_by": created_by_email,
                    "created_at": current_timestamp,
                    "updated_by": "",
                    "updated_at": "",
                    "family": {
                        "familyname": f"{data['name']}'s Family",
                        "consentby": data["name"],
                        "consentdate": current_timestamp,
                        "monitoredby": monitoredby
                    },
                    "members": [member_doc]
                }

                insert_result = child_db_instance.insert_one_document(collection_name, new_family_doc)

                return {
                    "Message": "New family document created."
                }, 201

        except Exception as e:
            return {"Message": "Parent registration failed.", "Error": str(e)}, 500

#api6 
@userauth_namespace.route("/child-family-tree")
class ChildMongoRegister(Resource):
    @jwt_required()
    def post(self):
        try:
            data = request.get_json()
            if not data:
                return {"Message": "No input data provided."}, 400

            identity = get_jwt_identity()
            identity_data = json.loads(identity)
            family_id = identity_data.get("family_id")
            user_id = identity_data.get("user_id")

            if not family_id or not user_id:
                return {"Message": "Missing family_id or user_id in token."}, 400

            # Validate required fields
            required_fields = ["name", "familyrole", "dob", "address", "mobile","track"]
            missing_fields = [
                f for f in required_fields
                if f not in data or (f != "track" and not data[f])
            ]

            # Ensure 'track' is a boolean
            if "track" not in data or not isinstance(data["track"], bool):
                missing_fields.append("track")

            if missing_fields:
                return {"Message": f"Missing fields: {', '.join(missing_fields)}"}, 400

            # Get email from MySQL user_id
            primary_user = Users.query.filter_by(USER_ID=user_id).first()
            if not primary_user:
                return {"Message": "User not found in MySQL."}, 404

            updated_by_email = primary_user.USER_NAME
            current_timestamp = int(time.time())

            collection_name, _ = child_db_instance.device_db_collection("family")
            family_doc = child_db_instance.find_one_document(collection_name, {"family_id": family_id})

            if not family_doc:
                return {"Message": "Family not found in MongoDB."}, 404

            members = family_doc.get("members", [])
            if any(m.get("name", "").lower() == data["name"].lower() for m in members):
                return {"Message": f"Member '{data['name']}' already exists."}, 409
            
            if any(m.get("mobile", "") == data["mobile"] for m in members):
                return {"Message": f"Mobile number '{data['mobile']}' already exists."}, 409

            member_id = f"{family_id}-{str(len(members) + 1).zfill(2)}"

            new_member = {
                "member_id": member_id,
                "familyrole": data["familyrole"].lower(),
                "name": data["name"],
                "age": calculate_age(data["dob"]),
                "mobile": data["mobile"],
                # "occupation": data["occupation"],
                "address": data["address"],
                "track": data.get("track")
            }

            # if data["occupation"].lower() == "student" and data.get("grade"):
            #     new_member["grade"] = data["grade"]

            members.append(new_member)

            update_success = child_db_instance.update_one_document(
                collection_name,
                {"family_id": family_id},
                {
                    "$set": {
                        "members": members,
                        "updated_by": updated_by_email,
                        "updated_at": current_timestamp
                    }
                }
            )

            if not update_success:
                return {"Message": "Failed to update family document."}, 500

            return {
                "Message": "Child added successfully."
            }, 201

        except Exception as e:
            return {"Message": "Child registration failed.", "Error": str(e)}, 500

@userauth_namespace.route("/family-details")
class FamilyTreeView(Resource):
    @jwt_required()
    def get(self):
        try:
            # Extract identity from JWT
            identity = get_jwt_identity()
            identity_data = json.loads(identity)
            family_id = identity_data.get("family_id")

            if not family_id:
                return {"Message": "Missing family_id in token."}, 400

            # Fetch the family document from MongoDB based on family_id
            collection_name, _ = child_db_instance.device_db_collection("family")
            family_doc = child_db_instance.find_one_document(collection_name, {"family_id": family_id})

            if not family_doc:
                return {"Message": "Family not found in MongoDB."}, 404

            # Get the members of the family
            members = family_doc.get("members", [])
            monitored_by = family_doc["family"].get("monitoredby", [])

            guardians = []
            children = []

            # Loop through members to categorize as guardians or children
            for member in members:
                role = member.get("familyrole", "").lower()
                name = member.get("name")
                
                if name in monitored_by:
                    # Add to guardians if the name is in the monitoredby list
                    guardians.append({"name": name})
                elif role in ["son", "daughter"]:
                    # Add to children if the role is son or daughter
                    children.append({"name": name})

            return {
                "guardians": guardians,
                "children": children
            }, 201

        except Exception as e:
            return {"Message": "Failed to fetch family tree.", "Error": str(e)}, 500

@userauth_namespace.route("/child-mobile")
class GetChildMobile(Resource):
    @jwt_required()
    def get(self):
        try:
            # Extract identity from JWT
            identity = get_jwt_identity()

            # Convert from string to dict if needed0
            if isinstance(identity, str):
                identity = json.loads(identity)

            # Extract the family_id from JWT
            family_id = identity.get("family_id")
            if not family_id:
                return {"Message": "Invalid or missing family ID in token."}, 400

            # Get 'member_name' from query parameters
            member_name = request.args.get('member_name')
            if not member_name:
                return {"Message": "Missing 'member_name' query parameter."}, 400

            # Fetch the family document from MongoDB
            collection_name, _ = child_db_instance.device_db_collection("family")
            family_doc = child_db_instance.find_one_document(collection_name, {"family_id": family_id})

            if not family_doc:
                return {"Message": "Family not found in MongoDB."}, 404

            members = family_doc.get("members", [])

            # Search for the member by name (case-sensitive exact match)
            for member in members:
                if member.get("name") == member_name:
                    return {
                        # "member_name": member.get("name"),
                        "mobile": member.get("mobile", "Not available"),
                        # "familyrole": member.get("familyrole", "unknown"),
                        # "track": member.get("track", False)
                    }, 201

            return {"Message": f"Member '{member_name}' not found in family members."}, 404

        except Exception as e:
            return {"Message": "Error fetching mobile number.", "Error": str(e)}, 500


from collections import defaultdict

@userauth_namespace.route("/plans")
class GroupedPlanList(Resource):
    def get(self):
        try:
            plans = Plan.query.all()
            grouped_response = defaultdict(list)

            for plan in plans:
                plan_type = plan.plan_type
                description = plan.description
                features = {
                    "Location Tracking": bool(plan.location_tracking),
                    "Call Details": bool(plan.call_details),
                    "SMS Details": bool(plan.sms_details),
                    "App Usage": bool(plan.app_usage),
                    "Contact Details": bool(plan.contact_details)
                }

                grouping_key = (description, tuple(features.items()))
                existing_group = None

                for group in grouped_response[plan_type]:
                    if group["description"] == description and group["features"] == features:
                        existing_group = group
                        break

                if existing_group:
                    existing_group["plans"].append({
                        "duration": plan.duration,
                        "charges": float(plan.charges)
                    })
                else:
                    grouped_response[plan_type].append({
                        "description": description,
                        "features": features,
                        "plans": [{
                            "duration": plan.duration,
                            "charges": float(plan.charges)
                        }]
                    })

            # Sort the plans by duration inside each group
            for plan_type_groups in grouped_response.values():
                for group in plan_type_groups:
                    group["plans"].sort(key=lambda x: x["duration"])

            return grouped_response, 201

        except Exception as e:
            return {"Message": "Failed to fetch grouped plans", "Error": str(e)}, 500


@userauth_namespace.route("/login")
class UserLogin(Resource):
    @userauth_namespace.expect(login_model, validate=True)
    @userauth_namespace.doc(responses={
        200: "Login successful",
        400: "Missing USER_NAME or USER_PASSWORD",
        401: "Invalid credentials",
        403: "Only GUEST or PARENT users are allowed to log in"
    })
    def post(self):
        data = request.get_json()
        email = data.get('USER_NAME')
        user_password = data.get('USER_PASSWORD')
 
        if not email or not user_password:
            return {"Message": "USER_NAME (email) and USER_PASSWORD are required"}, 400
 
        user = Users.get_user_by_email(email)
        if not user or not verify_password(user_password, user.USER_PASSWORD):
            return {"Message": "Invalid USER_NAME or USER_PASSWORD"}, 401
 
        # Role-based token expiration using if-elif
        if user.USER_ROLES == 'GUEST':
            expiration_days = 14
        elif user.USER_ROLES == 'MASTER':
            expiration_days = 30
        else:
            return {"Message": "Only GUEST or MASTER users are allowed to log in."}, 403
 
        expiration_minutes = expiration_days * 24 * 60
 
        # Generate tokens
        identity_payload = f"{user.USER_NAME},{user.USER_ROLES}"
        access_token = generate_jwt_access_token(identity_payload, expiration_minutes=expiration_minutes)
        refresh_token = generate_jwt_refresh_token(identity_payload)
 
        # Update LAST_LOGIN
        user.LAST_LOGIN = int(time.time())
        user.LAST_LOGIN_IP = request.headers.get('X-Forwarded-For', request.remote_addr)
        user.save()
 
        return {
            "Message": "Logged in successfully",
            "tokens": {
                "access": access_token,
                "refresh": refresh_token,
            },
            "COUNTRY_CODE": user.COUNTRY_CODE,
            "USER_ROLE":user.USER_ROLES
        }, 201


 
