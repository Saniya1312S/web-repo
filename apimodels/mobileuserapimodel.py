#apimodels.mobileuserapimodel.py
from flask_restx import fields
from extensions import api

# Base user model with common fields for both guest and subscription
class BaseUserModel:
    USER_NAME = fields.String(required=True, description="User Name (Email format)", pattern="^[\w\.-]+@[\w\.-]+\.\w+$")
    USER_PASSWORD = fields.String(required=True, description="Password")
    COUNTRY_CODE = fields.String(required=True, description="Country Code")

# Subscription user model
class SubscriptionUserModel(BaseUserModel):
    USER_ID = fields.String(required=True, description="User ID")
    FAMILY_ID = fields.String(required=True, description="Family ID")
    USER_FULL_NAME=fields.String(required=True, description="User Full Name")
    USER_ROLES = fields.String(required=True, description="User Role (Guest or Subscription)")
    AADHAR_DETAILS = fields.String(required=True, description="Aadhar Details")
    DATE_OF_BIRTH = fields.String(required=True, description="Date of Birth")
    COUNTRY_CODE = fields.String(required=True, description="Country Code")

# Guest user model (No Aadhar, Date of Birth, or User Roles)
class GuestUserModel(BaseUserModel):
    USER_NAME = fields.String(required=True, description="User Name")
    USER_PASSWORD = fields.String(required=True, description="Password")
    COUNTRY_CODE = fields.String(required=True, description="Country Code")

class NewMonitoredByModel:
    primary_user_name = fields.String(required=True, description="Primary user email for authentication", pattern="^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$")
    primary_user_password = fields.String(required=True, description="Primary user's password")
    
    USER_NAME = fields.String(required=True, description="Email of the new monitored_by user", pattern="^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$")
    USER_FULL_NAME = fields.String(required=True, description="Full name of the new monitored_by user")
    USER_PASSWORD = fields.String(required=True, description="Password for the new monitored_by user")
    USER_ROLES = fields.String(required=True, description="Role of the new monitored_by user (e.g., UNCLE, AUNT)")
    AADHAR_DETAILS = fields.String(required=True, description="Aadhar number of the new user")
    DATE_OF_BIRTH = fields.String(required=True, description="Date of Birth (YYYY-MM-DD)")
    PHONE_NUMBER = fields.String(required=True, description="Phone number of the new user")
    COUNTRY_CODE = fields.String(required=True, description="Country code (e.g., +91)")

# Login model
login_model = api.model("LoginModel", {
    "USER_NAME": fields.String(required=True, description="User Name (Email format)"),
    "USER_PASSWORD": fields.String(required=True, description="Password")
})












