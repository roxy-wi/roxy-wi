import os
import sys
import traceback

from app.modules.roxywi.exception import RoxywiConflictError


def out_error(error):
	error = str(error)
	exc_type, exc_obj, exc_tb = sys.exc_info()
	file_name = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
	stk = traceback.extract_tb(exc_tb, 1)
	function_name = stk[0][2]
	error = f'{error} in function: {function_name} in file: {file_name}'
	raise Exception(f'error: {error}')


def not_unique_error(error):
	if error.args[0] == 1062:
		col = error.args[1].split('key ')[1]
	else:
		col = error.args[0].split(': ')[-1]
	raise RoxywiConflictError(f'{col} must be uniq')
