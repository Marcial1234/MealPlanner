from webapp2_extras import sessions, auth
from webapp2_extras.auth import InvalidPasswordError, InvalidAuthIdError

from google.appengine.ext import ndb
from google.appengine.api import mail

from models import User, MealPlan, Meal, Food

import urllib, hashlib, webapp2, logging, jinja2, time, json, yaml, os

with open('conf') as config_file:
	config =  yaml.safe_load(config_file.read())

route = webapp2.Route
jinja_environment = jinja2.Environment(loader=
		jinja2.FileSystemLoader(os.path.dirname(__file__)))

def user_required(handler):
	"""
		Decorator that checks if there's a user associated with the current session.
		Will also fail if there's no session present.
	"""
	def check_login(self, *args, **kwargs):
		auth = self.auth
		if not auth.get_user_by_session():
			self.redirect(self.uri_for('login'))
		else:
			return handler(self, *args, **kwargs)

	return check_login

class BaseHandler(webapp2.RequestHandler):
	@webapp2.cached_property
	def auth(self):
		"""Shortcut to access the auth instance as a property."""
		return auth.get_auth()

	@webapp2.cached_property
	def user_info(self):
		"""Shortcut to access a subset of the user attributes that are stored
		in the session.

		The list of attributes to store in the session is specified in
			config['webapp2_extras.auth']['user_attributes'].
		:returns
			A dictionary with most user information
		"""
		return self.auth.get_user_by_session()

	@webapp2.cached_property
	def user(self):
		"""Shortcut to access the current logged in user.

		Unlike user_info, it fetches information from the persistence layer and
		returns an instance of the underlying model.

		:returns
			The instance of the user model associated to the logged in user.
		"""
		u = self.user_info
		return self.user_model.get_by_id(u['user_id']) if u else None

	@webapp2.cached_property
	def user_model(self):
		"""Returns the implementation of the user model.

		It is consistent with config['webapp2_extras.auth']['user_model'], if set.
		"""	 
		return self.auth.store.user_model

	@webapp2.cached_property
	def session(self):
			"""Shortcut to access the current session."""
			return self.session_store.get_session(backend="datastore")

	def render_template(self, view_filename, params=None):
		if not params:
			params = {}
		user = self.user
		params['user'] = user
		template = jinja_environment.get_template('views/%s.html' % view_filename)
		self.response.out.write(template.render(params))

	def display_message(self, message):
		"""Utility function to display a template with a simple message."""
		params = {
			'message': message
		}
		self.render_template('message', params)

	# this is needed for webapp2 sessions to work
	def dispatch(self):
			# Get a session store for this request.
			self.session_store = sessions.get_store(request=self.request)

			try:
				# Dispatch the request.
				webapp2.RequestHandler.dispatch(self)
			finally:
				# Save all sessions.
				self.session_store.save_sessions(self.response)

	def abort(self):
		NotFoundHandler(self)

	def send_mail(self, msg, msubject, email):
		message = mail.EmailMessage(sender="CoLabs Support {0}".format(config['mailers']['emails']),
                            subject=msubject)
		message.to = str(email)
		message.body = str(msg)
		message.html = str(msg)
		message.send()

class NotFoundHandler(BaseHandler):
	def get(self):
		self.render_template('404')

class MainHandler(BaseHandler):
	def get(self):
		if self.user:
			self.redirect(self.user.dashboard_link())
		else:
			params = { "splash" : True }
			self.render_template('login', params)

class SignupHandler(BaseHandler):
	def get(self):
		self.render_template('login')

	def post(self):
		email = self.request.get('email')
		name = self.request.get('name')
		password = self.request.get('password')
		last_name = self.request.get('lastname')

		unique_properties = ['email_address']
		user_data = self.user_model.create_user(email,
			unique_properties, email_address=email, name=name, password_raw=password,
			last_name=last_name, verified=False)
		if not user_data[0]: #user_data is a tuple
			self.display_message('Unable to create user for email %s because of \
				duplicate keys %s' % (email, user_data[1]))
			return
		
		user = user_data[1]
		user_id = user.get_id()

		token = self.user_model.create_signup_token(user_id)

		verification_url = self.uri_for('verification', type='v', user_id=user_id,
			signup_token=token, _full=True)

		msg = 'Verify your email address by visiting <a href="{url}">{url}</a>'

		self.send_mail( msg.format(url=verification_url), 'Verify your address', email)
		self.redirect(self.uri_for('home'))

class ForgotPasswordHandler(BaseHandler):
	def get(self):
		self.serve_page()

	def post(self):
		email = self.request.get('email')

		user = self.user_model.get_by_auth_id(email)
		if not user:
			logging.info('Could not find any user entry for email %s', email)
			self.serve_page(not_found=True)
			return

		user_id = user.get_id()
		token = self.user_model.create_signup_token(user_id)

		verification_url = self.uri_for('verification', type='p', user_id=user_id,
			signup_token=token, _full=True)

		msg = 'Reset your password by visiting <a href="{url}">{url}</a>'
		self.send_mail(msg.format(url=verification_url), 'Password Reset', email)
		self.redirect(self.uri_for('home'))
	
	def serve_page(self, not_found=False):
		email = self.request.get('email')
		params = {
			'email': email,
			'not_found': not_found
		}
		self.render_template('forgot', params)

class VerificationHandler(BaseHandler):
	def get(self, *args, **kwargs):
		user = None
		user_id = kwargs['user_id']
		signup_token = kwargs['signup_token']
		verification_type = kwargs['type']

		# it should be something more concise like
		# self.auth.get_user_by_token(user_id, signup_token)
		# unfortunately the auth interface does not (yet) allow to manipulate
		# signup tokens concisely
		user, ts = self.user_model.get_by_auth_token(int(user_id), signup_token,
			'signup')

		if not user:
			logging.info('Could not find any user with id "%s" signup token "%s"',
				user_id, signup_token)
			self.abort(404)

		# store user data in the session
		self.auth.set_session(self.auth.store.user_to_dict(user), remember=True)

		if verification_type == 'v':
			# remove signup token, we don't want users to come back with an old link
			self.user_model.delete_signup_token(user.get_id(), signup_token)

			if not user.verified:
				user.verified = True
				user.put()

			self.display_message('User email address has been verified.')
			return
		elif verification_type == 'p':
			# supply user to the page
			params = {
				'user': user,
				'token': signup_token
			}
			self.render_template('resetpassword', params)
		else:
			logging.info('verification type not supported')
			self.abort(404)

class SetPasswordHandler(BaseHandler):
	@user_required
	def post(self):
		password = self.request.get('password')
		old_token = self.request.get('t')

		if not password or password != self.request.get('confirm_password'):
			self.display_message('passwords do not match')
			return

		user = self.user
		user.set_password(password)
		user.put()

		# remove signup token, we don't want users to come back with an old link
		self.user_model.delete_signup_token(user.get_id(), old_token)
		
		self.display_message('Password updated')

class LoginHandler(BaseHandler):
	def get(self):
		if self.user:
			self.redirect(self.user.dashboard_link())
		else:
			self.serve_page()

	def post(self):
		email = self.request.get('email')
		# need to hash this thou
		password = self.request.get('password')
		try:
			u = self.auth.get_user_by_password(email, password, remember=True,
				save_session=True)
			self.redirect(self.uri_for('home'))
		except (InvalidAuthIdError, InvalidPasswordError) as e:
			logging.info('Login failed for user %s because of %s', email, type(e))
			self.serve_page(True)

	def serve_page(self, failed=False):
		email = self.request.get('email')
		params = {
			'email': email,
			'failed': failed
		}
		self.render_template('login', params)

class LogoutHandler(BaseHandler):
	def get(self):
		self.auth.unset_session()
		self.redirect(self.uri_for('home'))

# End Authentication/User [Creation/Deletion]

class dashboardHandler(BaseHandler):
	@user_required
	def get(self, *args, **kwargs):
		user_id = int(kwargs['user_id'])
		name = kwargs['name'].lower()
		request_type = kwargs['type'].lower()
		last_name = kwargs['last_name'].lower()

		local_user = User.get_by_id(user_id)
		if len(local_user.mealPlans) != 0:
			mealplans = [MealPlan.get_by_id(int(hope)) 
						for hope in local_user.mealPlans
						if MealPlan.get_by_id(int(hope)) != None]

			# fuck it, ship it

			# categorize each meal per plan
		else:
			mealplans = None
			# meals = None
		
		user = self.user
		if request_type == 'u':
			if local_user and local_user.name.lower() == name and local_user.key.id() == user_id:
				params = {
				# 'meals': meals,
				'user_id': user_id,
				'dashboard': True,
				'mealplans': mealplans,
				'local_user': local_user,
				'foodNames': Food.query().fetch()
				}
				# meal plans GO HERE
				self.render_template('dashboard', params)
			else:
				self.display_message('The user who\'s dashboard you attempted to view does not exist. <a href="/u/{0}.{1}/{2}">Go to your dashboard.</a>'.format(user.name, user.last_name, user.key.id()))
		else:
			self.redirect(self.uri_for('home'))

# Creation

class UserPreferenceHandler(BaseHandler):
	def get(self):
		# use tooltip to deliniate this. cog favicon, screw it
		# go to main to change this, it's commented there already
		params = {'user': self.user}
		self.render_template("preferences",params)

	def post(self):
		time.sleep(0.1)
		self.redirect(self.uri_for('home'))
		dietType = str(self.request.get('dietType'))
		weightInLb = float(self.request.get('weightInLb'))
		proteinRatio = float(self.request.get('proteinRatio'))
		carbRatio = float(self.request.get('carbRatio'))
		fatRatio = float(self.request.get('fatRatio'))

		PUTO_USER_ID = self.user.key.id()
		local_user = User.get_by_id(PUTO_USER_ID)

		local_user.dietType = dietType 
		local_user.weightInLb = weightInLb
		local_user.proteinRatio = proteinRatio
		local_user.carbRatio = carbRatio
		local_user.fatRatio = fatRatio

		# ok i think
		local_user.put()

class NewMealPlanHandler(BaseHandler):
	def post(self):
		# a lot of stuff to try. u['user_id'], etc
		name = self.request.get('name')
		user_id = int(self.request.get('user'))
		local_user = User.get_by_id(user_id)

		mealplan = MealPlan(name=name)
		mealplan.put()

		# this works!
		local_user.mealPlans.append(int(mealplan.key.id()))
		local_user.put()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))

class NewMealHandler(BaseHandler):
	def post(self):
		name = self.request.get('name')
		plan_id = int(self.request.get('plan'))
		local_plan = MealPlan.get_by_id(plan_id)
		
		meal = Meal(name=name)
		meal.put()

		local_plan.meals.append(int(meal.key.id()))

		local_plan.calories += meal.calories
		local_plan.protein += meal.protein
		local_plan.carbs += meal.carbs
		local_plan.fat += meal.fat

		local_plan.put()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))	

class NewFoodHandler(BaseHandler):
	def get(self):
		# LEAVE THIS
		self.render_template('food_form')

	def post(self):
		name = str(self.request.get('name'))
		amount = float(self.request.get('amount'))

		# all food content will be based on 1 OZ of weight
		scalar = 1/1

		calories = float(self.request.get('calories'))*scalar
		protein = float(self.request.get('protein'))*scalar
		carbs = float(self.request.get('carbs'))*scalar
		fat = float(self.request.get('fat'))*scalar

		food = Food(name=name, amount=amount, calories=calories, 
			protein=protein, carbs=carbs, fat=fat)
		food.put()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))

class AddFoodHandler(BaseHandler):
	def post(self):
		[name, food_id] = str(self.request.get('food')).split("+")
		meal_id = int(self.request.get('meal'))
		local_meal = Meal.get_by_id(meal_id)

		food = Food.get_by_id(int(food_id))
		local_meal.foods.append(int(food.key.id()))

		local_meal.calories += food.calories
		local_meal.protein += food.protein
		local_meal.carbs += food.carbs
		local_meal.fat += food.fat

		local_meal.put()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))	

# Deletion

class DeleteMealPlanHandler(BaseHandler):
	def post(self):
		key = int(self.request.get("id"))
		plan = MealPlan.get_by_id(key)
		plan.key.delete()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))	

class DeleteMealHandler(BaseHandler):
	def post(self):
		key = int(self.request.get("id"))
		meal = Meal.get_by_id(key)
		meal.key.delete()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))	

class DeleteFoodHandler(BaseHandler):
	def post(self):
		key = int(self.request.get("id"))
		food = Food.get_by_id(key)
		food.key.delete()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))

# how => works, if used
class EraseFoodHandler(BaseHandler):
	def post(self):
		key = int(self.request.get("id"))
		food = Food.get_by_id(key)
		food.key.delete()

		time.sleep(0.1)
		self.redirect(self.uri_for('home'))	



routes = [
		route('/', MainHandler, name='home'),
		route('/signup', SignupHandler),
		route('/<type:v|p>/<user_id:\d+>-<signup_token:.+>',
			handler=VerificationHandler, name='verification'),
		route("/dashboard", MainHandler),
		route('/password', SetPasswordHandler),
		route('/login', LoginHandler, name='login'),
		route('/logout', LogoutHandler, name='logout'),
		route('/forgot', ForgotPasswordHandler, name='forgot'),
		route('/new_food', handler=NewFoodHandler, name='newfood'),
		route('/add_food', handler=AddFoodHandler, name='addfood'),
		route('/new_meal', handler=NewMealHandler, name='newfood'),
		route('/delete_mealplan', handler=DeleteMealPlanHandler, name='deletemealplan'),
		route('/delete_meal', handler=DeleteMealHandler, name='deletemealplan'),
		route('/delete_food', handler=DeleteFoodHandler, name='deletemealplan'),

		route('/erase_food', handler=DeleteMealPlanHandler, name='erasemealplan'),

		route('/new_mealplan', handler=NewMealPlanHandler, name='newfood'),
		route('/preferences', handler=UserPreferenceHandler, name='preferences'),
		route('/<type:u>/<name:.+>.<last_name:.+>/<user_id:\d+>', handler=dashboardHandler, name='dashboard'),

		("/.*", NotFoundHandler),
]

app = webapp2.WSGIApplication(routes, debug=True, config=config)

# you changed na mas preferences