from connexion.resolver import Controller

class GreetingController(Controller):

    __controllername__ = "greeting"
    def __init__(self):
        self.was_called = False

    def post_greeting(self, name):
        self.was_called = True
        data = {'greeting': 'Hello {name}'.format(name=name)}
        return data