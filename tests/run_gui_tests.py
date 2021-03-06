#!/usr/bin/env python

import subprocess, sys, io, json, re, codecs, tempfile, atexit, os

ANOTHER_VARIANT = "//another variant:"
EXPECT_LINE = "//expect: "

def args_str_to_list(args_str):
    def append_to_args(args, arg):
        if arg.isdigit():
            args.append(int(arg))
        else:
            args.append(arg)

    whitespaces = re.compile(r"\s+")
    quote_param = re.compile(r'"(\\.|[^"])+"')
    single_param = re.compile(r"'(\\.|[^'])+'")
    res = []
    pos = 0
    while pos < len(args_str):
        m = re.match(whitespaces, args_str[pos:])
        if m:
            pos += m.end(0)
            continue
        if args_str[pos] == ',':
            pos += 1
            continue
        m = re.match(quote_param, args_str[pos:])
        if m:
            res.append(args_str[pos + m.start(0):pos + m.end(0)])
            pos += m.end(0)
            continue
        m = re.match(single_param, args_str[pos:])
        if m:
            res.append(args_str[pos + m.start(0):pos + m.end(0)])
            pos += m.end(0)
            continue
        new_pos = args_str.find(",", pos)
        if new_pos == -1:
            append_to_args(res, args_str[pos:])
            break
        else:
            append_to_args(res, args_str[pos:new_pos])
            pos = new_pos
    return res

def extract_func_name_and_params(line_with_func_call):
    try:
        func_m = re.match('(?P<func_prefix>[^\(]+)\((?P<args>.*)\);$', line_with_func_call)
        args_str = func_m.group("args")
        args = args_str_to_list(args_str)
        return (func_m.group("func_prefix"), args)
    except AttributeError:
        sys.stderr.write("error happens with |%s|\n" % line_with_func_call)
        raise
    except Exception as e:
        raise type(e)(e.message + " happens with '%s'" % line_with_func_call)

(prefix, params) = extract_func_name_and_params("Test.mouseClick('MainWindow.centralwidget.pushButton', 'Qt.LeftButton', 67, 13);")
print("params %s" % params)
assert prefix == "Test.mouseClick"
assert params == ["'MainWindow.centralwidget.pushButton'", "'Qt.LeftButton'", 67, 13]

def compare_two_func_calls(f1_call, f2_call):
    (pref1, params1) = extract_func_name_and_params(f1_call)
    (pref2, params2) = extract_func_name_and_params(f2_call)
    if pref1 != pref2 or len(params1) != len(params2):
        return False
    i = -1
    for p1, p2 in zip(params1, params2):
        i += 1
        if type(p1) is int and type(p2) is int:
            continue
        if p1 != p2:
            sys.stderr.write("params not equal %s vs %s\n" % (p1, p2))
            return False
    return True

def prepare_script_for_os(script_path):
    if sys.platform == "darwin":
        tf = tempfile.NamedTemporaryFile(delete=False)
        with open(script_path, "r") as f:
            for line in f.readlines():
                if not line.startswith("Test.mouseClick('MainWindow.menubar"):
                    tf.write(line)

        def delete_tmp_file():
            print("delete tmp file")
            os.unlink(tf.name)
        atexit.register(delete_tmp_file)
        tf.close()
        return tf.name
    else:
        return script_path

qt_monkey_app_path = sys.argv[1]
test_app_path = sys.argv[2]
script_path = sys.argv[3]

script_path = prepare_script_for_os(script_path)
print("we run script from %s" % script_path)

monkey_cmd = [qt_monkey_app_path, "--script", script_path,
              "--exit-on-script-error",
              "--user-app", test_app_path]

monkey = subprocess.Popen(monkey_cmd, stdout=subprocess.PIPE,
                          stdin=subprocess.PIPE, stderr=sys.stderr)

code_listing = []
input_stream = codecs.getreader("utf-8")(monkey.stdout)
for line in input_stream:
    print("MONKEY: %s" % line)
#    print("Parsed json: %s" % json.loads(line))
    msg = json.loads(line)
    if type(msg) is dict:
        event = msg.get("event")
        if event:
            code = event["script"]
            for line in code.split("\n"):
                code_listing.append(line)

with open(script_path, "r") as fin:
    i = 0
    j = 0
    expect_lines = fin.readlines()
    while j < len(expect_lines):
        if i >= len(code_listing):
            sys.stderr.write("Unexpected end of actual result\n")
            sys.exit(1)
        line = expect_lines[j].strip()
        expect_seq = False
        if line.startswith(EXPECT_LINE):
            line = line[len(EXPECT_LINE):]
            expect_seq = True
        if not compare_two_func_calls(line, code_listing[i]):
            if (i + 1) < len(code_listing) and code_listing[i+1].startswith(ANOTHER_VARIANT) and compare_two_func_calls(line, code_listing[i + 1][len(ANOTHER_VARIANT):]):
                i += 1
            elif (j + 1) < len(expect_lines) and expect_lines[j + 1].startswith(EXPECT_LINE) and compare_two_func_calls(expect_lines[j + 1][len(EXPECT_LINE):], code_listing[i]):
                j += 1
            else:
                sys.stderr.write(("Line %d, expected\n`%s'\n, actual\n`%s'\n"
                                  "Full log:\n%s\n") % (i + 1, line, code_listing[i], "\n".join(code_listing)))
                sys.exit(1)
        i += 1
        j += 1
        while expect_seq and j < len(expect_lines) and expect_lines[j].startswith(EXPECT_LINE):
            j += 1
