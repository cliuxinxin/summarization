import pytest
from util import *

def test_get_load_path():
    assert get_load_path('models') == 'models/model_0300.tar'
    print('ok')
