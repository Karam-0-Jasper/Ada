from flask import Flask, render_template, request

app = Flask(__name__)

PASS_MARK = 50  # each subject needs 50 or more to pass


# Step 1: show the form (front-end)
@app.route("/")
def home():
    return render_template("index.html")


# Step 2: receive the form data and calculate the result (back-end)
@app.route("/result", methods=["POST"])
def result():
    name = request.form["name"]
    roll_no = request.form["roll_no"]
    degree = request.form["degree"]
    semester = request.form["semester"]

    # Read the five subject marks and turn them into numbers
    marks = []
    for i in range(1, 6):
        marks.append(int(request.form["sub" + str(i)]))

    total = sum(marks)                 # add all five marks
    percentage = total / 5             # each subject is out of 100, so 500 max
    passed = all(m >= PASS_MARK for m in marks)
    status = "PASS" if passed else "FAIL"

    return render_template(
        "result.html",
        name=name,
        roll_no=roll_no,
        degree=degree,
        semester=semester,
        marks=marks,
        total=total,
        percentage=round(percentage, 2),
        status=status,
        pass_mark=PASS_MARK,
    )


if __name__ == "__main__":
    app.run(debug=True)
