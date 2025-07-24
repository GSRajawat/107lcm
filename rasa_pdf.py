import os
import fitz  # PyMuPDF
import re
import pandas as pd

PDF_FOLDER = "c:/Users/GOVT LAW COLLEGE 107/Documents/exam/rasa_pdf"

def parse_pdf(path):
    doc = fitz.open(path)
    text = "\n".join([page.get_text() for page in doc])
    doc.close()

    students = re.split(r"\n?RollNo\.\:\s*", text)
    students = [s.strip() for s in students if s.strip()]

    all_data = []

    for s in students:
        lines = s.splitlines()
        lines = [line.strip() for line in lines if line.strip()]

        # Helper function to find the value after a given prefix
        def extract_after(label):
            for i, line in enumerate(lines):
                if line.startswith(label):
                    value = line.replace(label, "").strip()
                    if value:
                        return value
                    elif i+1 < len(lines):
                        return lines[i+1].strip()
            return ""

        roll_no = re.match(r"(\d{9})", lines[0]).group(1) if re.match(r"(\d{9})", lines[0]) else ""
        enrollment = extract_after("Enrollment No.:")
        session = extract_after("Session:")
        regular = extract_after("Regular/ Backlog:")
        student_name = extract_after("Name:")
        father = extract_after("Father's Name:")
        mother = extract_after("Mother's Name:")
        gender = extract_after("Gender:")
        exam_name = extract_after("Exam Name:")
        centre = extract_after("Exam Centre:")
        college = extract_after("College Nmae:")
        address = extract_after("Address:")

        # Extract all paper descriptions containing [paper code]
        papers = re.findall(r"([^\n]+?\[\d{5}\][^\n]*)", s)

        student_data = {
            "Roll Number": roll_no,
            "Enrollment Number": enrollment,
            "Session": session,
            "Regular/Backlog": regular,
            "Name": student_name,
            "Father's Name": father,
            "Mother's Name": mother,
            "Gender": gender,
            "Exam Name": exam_name,
            "Exam Centre": centre,
            "College Name": college,
            "Address": address
        }

        for i, paper in enumerate(papers[:10]):
            student_data[f"Paper {i+1}"] = paper.strip()

        all_data.append(student_data)

    return all_data


# Process all PDFs in rasa_pdf folder
all_students = []
for filename in os.listdir(PDF_FOLDER):
    if filename.lower().endswith(".pdf"):
        pdf_path = os.path.join(PDF_FOLDER, filename)
        print(f"📄 Extracting: {filename}")
        all_students.extend(parse_pdf(pdf_path))

# Convert to DataFrame and save
df = pd.DataFrame(all_students)
df.to_csv("c:/Users/GOVT LAW COLLEGE 107/Documents/exam/attestation_data_combined.csv", index=False)
print("✅ Data saved to attestation_data_combined.csv")
