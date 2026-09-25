import app.modules.common.common as common


def show_log(stdout, **kwargs):
	i = 0
	out = ''
	grep = kwargs.get('grep')

	if grep:
		grep = common.sanitize_input_word(grep)
	for line in stdout:
		i = i + 1
		if grep:
			line = common.highlight_word(line, grep)
		line_class = "line3" if i % 2 == 0 else "line"
		out += common.wrap_line(line, line_class)

	return out
