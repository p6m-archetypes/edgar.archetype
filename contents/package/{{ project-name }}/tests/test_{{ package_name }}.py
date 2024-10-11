from unittest import TestCase
import {{ project_name }}.{{ package_name }} as {{ package_name }}


class Test(TestCase):
    def test_execute(self):
        {{ package_name }}.execute()
        print("It works!")
