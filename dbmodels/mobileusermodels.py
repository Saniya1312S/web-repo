# dbmodels.mobileusermodels.py
from extensions import db
from uuid import uuid4

# Model for Mobile login users
class Users(db.Model):
    __tablename__ = "mobile_user"
    
    ACTIVE = db.Column(db.Boolean, nullable=False)
    USER_ID = db.Column(db.String(100), default=str(uuid4()))
    FAMILY_ID = db.Column(db.String(45), nullable=True)
    USER_NAME = db.Column(db.String(100), primary_key=True, nullable=False)
    USER_FULL_NAME=db.Column(db.String(45), nullable=True)
    USER_PASSWORD = db.Column(db.String(100), nullable=False)
    USER_TOKEN = db.Column(db.String(1000), nullable=True)  # Matches SQL schema
    USER_ROLES = db.Column(db.String(100), nullable=True)
    LAST_LOGIN = db.Column(db.BigInteger, nullable=True)
    LAST_PASSWORD_CHANGE = db.Column(db.BigInteger, nullable=True)
    UPDATED_BY = db.Column(db.String(100), nullable=True)
    UPDATED_AT = db.Column(db.BigInteger, nullable=True)
    CREATED_BY = db.Column(db.String(100), nullable=False)
    CREATED_AT = db.Column(db.BigInteger, nullable=False)
    LAST_LOGIN_IP = db.Column(db.String(100), nullable=True)
    SUBSCRIPTION_DURATION = db.Column(db.Integer, nullable=True)
    USER_TOKEN_EXPIRY_DATE = db.Column(db.BigInteger, nullable=True)
    AADHAR_DETAILS = db.Column(db.String(45), nullable=True)
    DATE_OF_BIRTH = db.Column(db.String(20), nullable=True)
    PHONE_NUMBER = db.Column(db.String(10), nullable=True)
    COUNTRY_CODE = db.Column(db.String(4), nullable=False)

    def __repr__(self):
        return f"<UserId - {self.USER_ID} UserName - {self.USER_NAME}>"
    
    @classmethod
    def get_user_by_user_id(cls, user_id):
        return cls.query.filter_by(USER_ID=user_id).first()

    @staticmethod
    def get_user_by_email(email):
        return Users.query.filter_by(USER_NAME=email).first()  # Get user by email
    @staticmethod
    def get_user_by_phone(phone_number):
        return Users.query.filter_by(PHONE_NUMBER=phone_number).first()

    
    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()


class UserMask(db.Model):
    __tablename__ = 'usermask'  # This is the table name in your database
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_name = db.Column(db.String(100), nullable=False)
    Tokenid = db.Column(db.String(50), nullable=False, unique=True)
    Tokenvalue = db.Column(db.String(50), nullable=False)

    def __init__(self, user_name, Tokenid, Tokenvalue):
        self.user_name = user_name
        self.Tokenid = Tokenid
        self.Tokenvalue = Tokenvalue

    def save(self):
        """Save the mapping to the database."""
        db.session.add(self)
        db.session.commit()

    @staticmethod
    def get_token_for_value(cls, user_name, Tokenvalue):
        """Fetch the token for the given user_name and Tokenvalue."""
        return cls.query.filter_by(user_name=user_name, Tokenvalue=Tokenvalue).first()

    @staticmethod
    def get_value_for_token(tokenid):
        # Query the database to find the token entry
        return UserMask.query.filter_by(Tokenid=tokenid).first()  # Make sure Tokenid is correctly queried


class Subscriptions(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.String(100), primary_key=True)  # Changed from `subscription_id` to `id`
    user_id = db.Column(db.String(100), nullable=False)
    plan_id = db.Column(db.String(100), nullable=False)
    subscription_status = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.BigInteger, nullable=False)
    end_date = db.Column(db.BigInteger, nullable=False)
    renewal_date = db.Column(db.BigInteger, nullable=True)
    subscription_type = db.Column(db.String(50), nullable=True)
    payment_type = db.Column(db.String(50), nullable=True)
    payment_id = db.Column(db.String(45), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    auto_renewal_flag = db.Column(db.Boolean, default=False)
    discount_id = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.BigInteger, nullable=False)
    updated_at = db.Column(db.BigInteger, nullable=False)
    cancellation_date = db.Column(db.BigInteger, nullable=True)
    cancellation_reason = db.Column(db.String(100), nullable=True)
    usage_limits = db.Column(db.String(100), nullable=True)
    origin = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f"<Subscription ID: {self.id} | User ID: {self.user_id} | Plan ID: {self.plan_id}>"

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

class Plan(db.Model):
    __tablename__ = 'plans'

    plan_id = db.Column(db.String(5), primary_key=True)
    duration = db.Column(db.Integer, nullable=False)
    plan_type = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=True)
    charges = db.Column(db.Numeric(10, 2), nullable=False)
    location_tracking = db.Column(db.Boolean, default=False)
    call_details = db.Column(db.Boolean, default=False)
    sms_details = db.Column(db.Boolean, default=False)
    app_usage = db.Column(db.Boolean, default=False)
    contact_details = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Plan ID: {self.plan_id} | Type: {self.plan_type} | Duration: {self.duration} months>"

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()


class DiscountOffer(db.Model):
    __tablename__ = 'discount_offer'

    discount_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    discount_code = db.Column(db.String(20), nullable=False)
    plan_id = db.Column(db.String(5), db.ForeignKey('plans.plan_id'), nullable=False)
    start_date = db.Column(db.BigInteger, nullable=False)  # Unix timestamp
    end_date = db.Column(db.BigInteger, nullable=False)    # Unix timestamp
    status = db.Column(db.Boolean, nullable=False, default=True)
    discount_pct = db.Column(db.Numeric(5, 2), nullable=False)
    discount_amount = db.Column(db.String(10), nullable=False)

    # Optional relationship if you want to access plan details from a discount
    plan = db.relationship('Plan', backref='discounts', lazy=True)

    def __repr__(self):
        return f"<Discount ID: {self.discount_id} | Code: {self.discount_code} | Plan ID: {self.plan_id}>"

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

class Payment(db.Model):
    __tablename__ = 'payments'

    payment_id = db.Column(db.String(100), primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_status = db.Column(db.String(20), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)
    payment_date = db.Column(db.BigInteger, nullable=False)  # Unix timestamp
    payment_type = db.Column(db.String(45), nullable=True)

    def __repr__(self):
        return f"<Payment ID: {self.payment_id} | User ID: {self.user_id} | Status: {self.payment_status}>"

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()





