import time, urllib, hashlib
import webapp2_extras.appengine.auth.models

from google.appengine.ext import ndb
from webapp2_extras import security


class User(webapp2_extras.appengine.auth.models.User):
  mealPlans = ndb.StringProperty(repeated=True)
  dietType = ndb.StringProperty(required=False)
  # Error is made as required, for now
  weightInLb = ndb.FloatProperty()
  proteinRatio = ndb.FloatProperty()
  carbRatio = ndb.FloatProperty()
  fatRatio = ndb.FloatProperty()

  # SHA1 encryption
  def set_password(self, raw_password):
    self.password = security.generate_password_hash(raw_password, length=12)

  def profile_link(self):
    return "/u/{0}.{1}/{2}".format(self.name, self.last_name, self.key.id())

  def gravatarize(self):
    default = ""
    gravatar_url = "http://www.gravatar.com/avatar/" + hashlib.md5(self.email_address.lower()).hexdigest() + "?"
    gravatar_url += urllib.urlencode({'d':default, 's':str(200)})
    return gravatar_url

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

class Lab(ndb.Model):
  name = ndb.StringProperty(required=True)
  collaborators = ndb.StringProperty(repeated=True)
  owner = ndb.StringProperty(required=True)
  private = ndb.BooleanProperty()
  
  def destroy_url(self):
    return '/l/delete?id=%s' % self.key.id()
  
  def lab_link(self):
    return "/l/{0}".format(self.key.id())

  def list_collaborators(self):
    users = []
    for collaborator in self.collaborators:
      user = User.get_by_auth_id(collaborator)
      if user:
        users.append(user)
      else:
        users.append('{0}'.format(collaborator))
    return users


# type of diet formulae!
# based on your weight, and diet type

class MealPlan(ndb.Model):
    meals = ndb.StringProperty(repeated=True)
    title = ndb.StringProperty(required=True)
    calories = ndb.FloatProperty(required=True)
    protein = ndb.FloatProperty(required=True)
    carbs = ndb.FloatProperty(required=True)
    fat = ndb.FloatProperty(required=True)
    proteinTarget = ndb.FloatProperty(required=True)
    carbsTarget = ndb.FloatProperty(required=True)
    fatTarget = ndb.FloatProperty(required=True)


class Meal(ndb.Model):
    foods = ndb.StringProperty(repeated=True)
    title = ndb.StringProperty(required=True)
    calories = ndb.FloatProperty(required=True)
    protein = ndb.FloatProperty(required=True)
    carbs = ndb.FloatProperty(required=True)
    fat = ndb.FloatProperty(required=True)


class Food(ndb.Model):
    # figure out 
    title = ndb.StringProperty(required=True, repeated=False)
    calories = ndb.FloatProperty(required=True)
    protein = ndb.FloatProperty(required=True)
    carbs = ndb.FloatProperty(required=True)
    fat = ndb.FloatProperty(required=True)