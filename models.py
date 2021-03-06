import time, urllib, hashlib
import webapp2_extras.appengine.auth.models

from google.appengine.ext import ndb
from webapp2_extras import security

class User(webapp2_extras.appengine.auth.models.User):
  mealPlans = ndb.FloatProperty(repeated=True)
  
  weightInLb = ndb.FloatProperty(default=0)
  proteinRatio = ndb.FloatProperty(default=0)
  carbRatio = ndb.FloatProperty(default=0)
  fatRatio = ndb.FloatProperty(default=0)

  caloriesTarget = ndb.FloatProperty(required=True, default=0)
  proteinTarget = ndb.FloatProperty(required=True, default=0)
  carbsTarget = ndb.FloatProperty(required=True, default=0)
  fatTarget = ndb.FloatProperty(required=True, default=0)
  
  def getPreferences(self):
    self.proteinTarget = self.weightInLb * self.proteinRatio
    self.carbsTarget = self.weightInLb * self.carbRatio
    self.fatTarget =  self.weightInLb * self.fatRatio
    self.caloriesTarget = self.proteinTarget * 4 + self.carbsTarget * 4 + self.fatTarget * 8

    return [self.caloriesTarget, self.proteinTarget, self.carbsTarget, self.fatTarget ]


  # SHA1 encryption
  def set_password(self, raw_password):
    self.password = security.generate_password_hash(raw_password, length=12)

  def dashboard_link(self):
    return "/u/{0}.{1}/{2}".format(self.name, self.last_name, self.key.id())

  @classmethod
  def get_by_auth_token(cls, user_id, token, subject='auth'):
    """
    Returns a user object based on a user ID and token.

    :param user_id:
        The user_id of the requesting user.
    :param token:
        The token string to be verified.
    :returns:
        A tuple ``(User, timestamp)``, with a user object and
        the token timestamp, or ``(None, None)`` if both were not found.
    """
    token_key = cls.token_model.get_key(user_id, subject, token)
    user_key = ndb.Key(cls, user_id)

    # Use get_multi() to save a RPC call.
    valid_token, user = ndb.get_multi([token_key, user_key])
    if valid_token and user:
        timestamp = int(time.mktime(valid_token.created.timetuple()))
        return user, timestamp

    return None, None

class MealPlan(ndb.Model):
    meals = ndb.FloatProperty(repeated=True)

    name = ndb.StringProperty(required=True)
    calories = ndb.FloatProperty(required=True, default=0)
    protein = ndb.FloatProperty(required=True, default=0)
    carbs = ndb.FloatProperty(required=True, default=0)
    fat = ndb.FloatProperty(required=True, default=0)

    # targets
    def getMeals(self):
        return [Meal.get_by_id(int(hope))
                for hope in self.meals
                if Meal.get_by_id(int(hope)) != None]

    def sum_everything(self):
        for m in self.meals:
            meal = Meal.get_by_id(int(m))
            
            if meal != None:
                self.calories += meal.calories
                self.protein += meal.protein
                self.carbs += meal.carbs
                self.fat += meal.fat
        
        return [self.calories, self.protein, self.carbs, self.fat]

class Meal(ndb.Model):
    foods = ndb.FloatProperty(repeated=True)
    
    name = ndb.StringProperty(required=True)
    calories = ndb.FloatProperty(required=True, default=0)
    protein = ndb.FloatProperty(required=True, default=0)
    carbs = ndb.FloatProperty(required=True, default=0)
    fat = ndb.FloatProperty(required=True, default=0)

    def getFoods(self):
        return [Food.get_by_id(int(hope))
                for hope in self.foods
                if Food.get_by_id(int(hope)) != None]
  
class Food(ndb.Model):
    name = ndb.StringProperty(required=True)
    amount = ndb.FloatProperty(required=True)
    calories = ndb.FloatProperty(required=True)
    protein = ndb.FloatProperty(required=True)
    carbs = ndb.FloatProperty(required=True)
    fat = ndb.FloatProperty(required=True)