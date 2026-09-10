"""Column detection for imported member/billing/trainer spreadsheets.

Gym platforms each name their export columns differently, and only GymMaster
publishes its template. So rather than hardcode one schema per vendor, every
canonical field carries a list of header aliases collected from the formats we
know (GymMaster's `member_firstname` style, FitnessForce/Torzil/GymForce's
"First Name" style, and the generic exports most tools produce). Headers are
normalised before matching, so "First Name", "first_name" and "FIRSTNAME" all
land on the same field.

Anything the detector gets wrong is fixable by hand in the preview step, which
is what makes this work for vendors whose exact headers we can't verify.
"""

import re

MEMBER = "members"
BILLING = "billing"
TRAINER = "trainers"


def normalise(header):
    """Lowercase, strip punctuation/spaces so header variants collapse to one
    key: "Member First Name" -> "memberfirstname"."""
    return re.sub(r"[^a-z0-9]", "", str(header or "").strip().lower())


# Canonical field -> accepted header aliases (already normalised on lookup).
MEMBER_FIELDS = {
    "first_name": [
        "firstname", "memberfirstname", "fname", "givenname", "first",
        "clientfirstname", "name",
    ],
    "last_name": [
        "lastname", "membersurname", "surname", "lname", "familyname", "last",
        "clientlastname",
    ],
    "email": ["email", "emailaddress", "memberemail", "clientemail", "primaryemail"],
    "phone": [
        "phone", "mobile", "mobileno", "mobilenumber", "phonenumber", "phoneno",
        "contact", "contactnumber", "contactno", "cell", "cellphone",
        "memberphone", "telephone", "tel", "whatsapp", "whatsappnumber",
    ],
    "date_of_birth": ["dateofbirth", "dob", "birthdate", "birthday", "memberdob"],
    "join_date": [
        "joindate", "joined", "joiningdate", "startdate", "membershipstartdate",
        "signupdate", "registrationdate", "datejoined", "memberjoindate",
    ],
    "membership_status": ["status", "membershipstatus", "memberstatus", "active", "state"],
    "emergency_contact_name": [
        "emergencycontact", "emergencycontactname", "emergencyname", "nextofkin",
    ],
    "emergency_contact_phone": [
        "emergencycontactphone", "emergencyphone", "emergencycontactnumber",
        "nextofkinphone",
    ],
    "username": ["username", "userid", "memberid", "membercode", "clientid", "code"],
}

BILLING_FIELDS = {
    "email": ["email", "emailaddress", "memberemail", "clientemail"],
    "username": ["username", "userid", "memberid", "membercode", "clientid", "code"],
    "member_name": ["member", "membername", "name", "client", "clientname", "fullname"],
    "plan": [
        "plan", "planname", "membership", "membershiptype", "membershipplan",
        "package", "packagename", "subscription", "producttype", "product",
    ],
    "amount": [
        "amount", "amountpaid", "paid", "price", "total", "totalamount", "value",
        "paymentamount", "fee", "grossamount",
    ],
    "method": [
        "method", "paymentmethod", "paymentmode", "mode", "paymenttype", "tendertype",
    ],
    "status": ["status", "paymentstatus", "transactionstatus"],
    "paid_date": [
        "paiddate", "date", "paymentdate", "transactiondate", "datepaid",
        "receiptdate", "invoicedate",
    ],
    "period_start": ["periodstart", "startdate", "fromdate", "validfrom", "membershipstart"],
    "period_end": [
        "periodend", "enddate", "todate", "validto", "expiry", "expirydate",
        "membershipend", "duedate",
    ],
    "external_reference": [
        "reference", "referenceno", "invoiceno", "invoicenumber", "receiptno",
        "receiptnumber", "transactionid", "txnid", "paymentid",
    ],
    "notes": ["notes", "note", "remarks", "comment", "comments", "description"],
}

TRAINER_FIELDS = {
    "first_name": ["firstname", "fname", "givenname", "first", "trainerfirstname"],
    "last_name": ["lastname", "surname", "lname", "familyname", "last", "trainersurname"],
    "name": ["name", "fullname", "trainername", "instructorname", "staffname", "employeename"],
    "email": ["email", "emailaddress", "traineremail", "staffemail", "workemail"],
    "phone": [
        "phone", "mobile", "mobileno", "mobilenumber", "phonenumber", "phoneno",
        "contact", "contactnumber", "contactno", "cell", "telephone", "tel",
    ],
    "specialty": [
        "specialty", "speciality", "specialization", "specialisation", "expertise",
        "discipline", "designation", "role", "jobtitle", "title",
    ],
    "bio": ["bio", "biography", "about", "description", "profile", "notes"],
    "username": ["username", "userid", "staffid", "employeeid", "trainerid", "code"],
}

FIELDS = {MEMBER: MEMBER_FIELDS, BILLING: BILLING_FIELDS, TRAINER: TRAINER_FIELDS}

REQUIRED = {
    # An account needs something to key on and something to call the person.
    MEMBER: ["first_name"],
    BILLING: ["amount"],
    TRAINER: ["name"],
}


def detect_columns(headers, kind):
    """Best-guess {canonical_field: header} for one sheet.

    Ambiguity is resolved by alias position: a field lists its strongest alias
    first, so "name" matching `first_name`'s weak trailing alias never beats a
    real "First Name" column. A header is claimed by at most one field.
    """
    fields = FIELDS[kind]
    normalised = {normalise(h): h for h in headers if str(h or "").strip()}

    scored = []
    for field, aliases in fields.items():
        for rank, alias in enumerate(aliases):
            if alias in normalised:
                scored.append((rank, field, normalised[alias]))
                break

    mapping = {}
    claimed = set()
    for _, field, header in sorted(scored):
        if header in claimed:
            continue
        mapping[field] = header
        claimed.add(header)
    return mapping
