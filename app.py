from flask import Flask, render_template, request, redirect, session, send_file, url_for
from models import db, User, Service, Stock, Bill, BillItem
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from urllib.parse import quote_plus
import pandas as pd
import io
import uuid

app = Flask(__name__)
app.secret_key = "rudra_secret"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rudra.db'
db.init_app(app)

AUTO_MATERIAL_RULES = [
    (("xerox",), "A4 Sheet"),
    (("photo", "photos", "passport"), "6x4 Sheet"),
]


def automatic_material_for_service(service_name, fallback=None):
    normalized_name = service_name.lower()
    for keywords, material in AUTO_MATERIAL_RULES:
        if any(keyword in normalized_name for keyword in keywords):
            return material
    return fallback

@app.context_processor
def inject_cart_count():
    cart = session.get('cart', {})
    total = 0
    for item in cart.values():
        if isinstance(item, dict):
            total += int(item.get('qty', 0))
        else:
            total += int(item)
    return {'cart_count': total}


def create_tables():
    db.create_all()

    # default users
    if not User.query.filter_by(username="admin").first():
        db.session.add(User(username="admin", password="admin"))
    if not User.query.filter_by(username="ganesh").first():
        db.session.add(User(username="ganesh", password="IT"))

    # default services
    default_services = [
        ("Single Side Xerox", 3.0, "A4 Sheet"),
        ("Double Side Xerox", 4.0, "A4 Sheet"),
        ("Color & Online Xerox", 10.0, "A4 Sheet"),
        ("ID Card Lamination", 50.0, "ID Lamination Sheet"),
        ("Aadhaar Card Lamination", 80.0, "Aadhaar Lamination Sheet"),
        ("A4 Lamination", 120.0, "A4 Lamination Sheet"),
        ("Passport size 4 Photos", 50.0, "6x4 Sheet"),
        ("Passport size 8 Photos", 80.0, "6x4 Sheet")
    ]
    for name, price, material in default_services:
        service = Service.query.filter_by(name=name).first()
        if not service:
            db.session.add(Service(name=name, price=price, material=material))
        else:
            service.material = automatic_material_for_service(name, material)

    # default stock items
    default_stock = [
        ("A4 Sheet", 500, 0.5, "Local Vendor", "Xerox"),
        ("ID Lamination Sheet", 100, 5.0, "Lamination Supplier", "Lamination"),
        ("Aadhaar Lamination Sheet", 100, 8.0, "Lamination Supplier", "Lamination"),
        ("A4 Lamination Sheet", 50, 10.0, "Lamination Supplier", "Lamination"),
        ("6x4 Sheet", 100, 5.0, "Photo Print Co.", "Photos")
    ]
    for name, qty, price, supplier, service_type in default_stock:
        stock = Stock.query.filter_by(name=name).first()
        if not stock:
            db.session.add(Stock(name=name, quantity=qty, price=price, supplier=supplier, service_type=service_type))
        else:
            stock.service_type = service_type

    # Keep older databases aligned with the automatic material rules.
    for service in Service.query.all():
        service.material = automatic_material_for_service(service.name, service.material)

    db.session.commit()

with app.app_context():
    create_tables()

# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']

        user = User.query.filter_by(username=u, password=p).first()
        if user:
            session['user'] = u
            return redirect('/')
    return render_template('login.html')

# ---------------- HOME ----------------
@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')
    services = Service.query.all()
    stock_info = {}
    for service in services:
        stock = Stock.query.filter_by(name=service.material).first() if service.material else None
        total_qty = stock.quantity if stock else 0
        stock_info[service.id] = total_qty
    return render_template('home.html', services=services, stock_info=stock_info)

# ---------------- CART ----------------
@app.route('/add-to-cart/<int:service_id>', methods=['POST'])
def add_to_cart(service_id):
    if 'user' not in session:
        return redirect('/login')

    service = Service.query.get(service_id)
    if not service:
        return redirect(url_for('home'))

    try:
        qty = int(request.form.get('qty', 1))
    except ValueError:
        qty = 1
    if qty < 1:
        qty = 1

    cart = session.get('cart', {})
    cart_key = str(service_id)
    
    if cart_key in cart and isinstance(cart[cart_key], dict):
        cart[cart_key]['qty'] += qty
    else:
        # Always use dict format for service items for consistency
        cart_item = {
            'qty': qty,
            'service_id': service_id,
            'is_service': True
        }
        cart[cart_key] = cart_item

    session['cart'] = cart
    return redirect(request.referrer or url_for('home'))

@app.route('/add-custom-service', methods=['POST'])
def add_custom_service():
    if 'user' not in session:
        return redirect('/login')

    name = request.form.get('custom_name', '').strip()
    try:
        price = float(request.form.get('custom_price', 0))
    except ValueError:
        price = 0.0
    try:
        qty = int(request.form.get('qty', 1))
    except ValueError:
        qty = 1

    if not name or price <= 0 or qty < 1:
        return redirect(request.referrer or url_for('home'))

    cart = session.get('cart', {})
    item_key = f"custom_{uuid.uuid4().hex}"
    cart[item_key] = {
        'qty': qty,
        'name': name,
        'price': price,
        'custom': True
    }
    session['cart'] = cart

    return redirect(request.referrer or url_for('home'))

@app.route('/cart')
def view_cart():
    if 'user' not in session:
        return redirect('/login')

    cart = session.get('cart', {})
    items = []
    total = 0

    for service_id, value in cart.items():
        if isinstance(value, dict):
            qty = int(value.get('qty', 0))
            if qty <= 0:
                continue
            
            # Check if it's a custom service or a service with selected stock
            if value.get('custom'):
                price = float(value.get('price', 0))
                items.append({
                    'custom': True,
                    'name': value.get('name', 'Custom Service'),
                    'price': price,
                    'quantity': qty,
                    'subtotal': price * qty,
                    'key': service_id
                })
                total += price * qty
            elif value.get('is_service'):
                service_id_int = int(value.get('service_id', 0))
                service = Service.query.get(service_id_int)
                if service:
                    stock_name = value.get('stock_name') or service.material or ''
                    subtotal = service.price * qty
                    items.append({
                        'custom': False,
                        'service': service,
                        'stock_name': stock_name,
                        'quantity': qty,
                        'subtotal': subtotal,
                        'key': service_id
                    })
                    total += subtotal
        else:
            # Handle old format (backwards compatibility)
            service = Service.query.get(int(service_id) if service_id.isdigit() else 0)
            if service and int(value) > 0:
                subtotal = service.price * int(value)
                items.append({
                    'custom': False,
                    'service': service,
                    'quantity': int(value),
                    'subtotal': subtotal,
                    'key': service_id
                })
                total += subtotal

    return render_template('cart.html', items=items, total=total)

@app.route('/cart/update', methods=['POST'])
def update_cart():
    if 'user' not in session:
        return redirect('/login')

    cart = session.get('cart', {})
    for key, value in request.form.items():
        if key.startswith('qty_'):
            item_key = key.split('_', 1)[1]
            try:
                qty = int(value)
            except ValueError:
                qty = 0
            if qty > 0:
                if item_key in cart and isinstance(cart[item_key], dict):
                    cart[item_key]['qty'] = qty
                else:
                    cart[item_key] = qty
            else:
                cart.pop(item_key, None)

    session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/cart/remove/<item_key>', methods=['POST'])
def remove_from_cart(item_key):
    if 'user' not in session:
        return redirect('/login')

    cart = session.get('cart', {})
    cart.pop(item_key, None)
    session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user' not in session:
        return redirect('/login')

    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('view_cart'))

    payment_method = request.form.get('payment_method', 'cash')
    phone = request.form.get('phone', '').strip()

    bill = Bill(total=0)
    db.session.add(bill)
    db.session.commit()

    total = 0
    total_profit = 0

    for service_id, value in cart.items():
        if isinstance(value, dict):
            qty = int(value.get('qty', 0))
            if qty <= 0:
                continue
            
            # Check if it's a custom service or a service with material selection
            if value.get('custom'):
                name = value.get('name', 'Custom Service')
                price = float(value.get('price', 0))
                subtotal = price * qty
                total += subtotal
                db.session.add(BillItem(
                    bill_id=bill.id,
                    service_name=name,
                    quantity=qty,
                    price=price
                ))
            elif value.get('is_service'):
                service_id_int = int(value.get('service_id', 0))
                service = Service.query.get(service_id_int)
                if not service:
                    continue
                
                stock_name = value.get('stock_name') or service.material or ''
                stock = Stock.query.filter_by(name=stock_name).first() if stock_name else None
                
                subtotal = service.price * qty
                total += subtotal
                cost_price = stock.price if stock else service.price
                profit = (service.price - cost_price) * qty
                total_profit += profit
                
                # Create bill item with service name and stock info if applicable
                display_name = f"{service.name} ({stock_name})" if stock_name else service.name
                db.session.add(BillItem(
                    bill_id=bill.id,
                    service_name=display_name,
                    quantity=qty,
                    price=service.price
                ))
                
                # Deduct from stock
                if stock:
                    stock.quantity -= qty
        else:
            # Handle old format (backwards compatibility)
            if not isinstance(value, int) or value <= 0:
                continue
            service = Service.query.get(int(service_id))
            if not service:
                continue
            qty = int(value)
            subtotal = service.price * qty
            total += subtotal
            stock = Stock.query.filter_by(name=service.material).first() if service.material else None
            cost_price = stock.price if stock else service.price
            profit = (service.price - cost_price) * qty
            total_profit += profit
            db.session.add(BillItem(
                bill_id=bill.id,
                service_name=service.name,
                quantity=qty,
                price=service.price
            ))
            if stock:
                stock.quantity -= qty

    if payment_method == 'online':
        online_fee = 4.0
        db.session.add(BillItem(
            bill_id=bill.id,
            service_name='Online Convenience Fee',
            quantity=1,
            price=online_fee
        ))
        total += online_fee

    bill.total = total
    db.session.commit()
    session.pop('cart', None)

    if phone:
        return redirect(url_for('send_whatsapp', bill_id=bill.id, phone=phone, method=payment_method))

    return redirect(url_for('invoice', id=bill.id))

@app.route('/send-whatsapp/<int:bill_id>')
def send_whatsapp(bill_id):
    bill = Bill.query.get(bill_id)
    if not bill:
        return redirect(url_for('home'))

    items = BillItem.query.filter_by(bill_id=bill_id).all()
    payment_method = request.args.get('method', 'cash')
    phone = request.args.get('phone', '')

    message_lines = [
        f"Rudra Computers Invoice #{bill.id}",
        f"Payment Method: {payment_method.capitalize()}",
        "",
    ]

    for item in items:
        message_lines.append(f"{item.service_name} x {item.quantity} = ₹{item.price * item.quantity}")

    message_lines.append("")
    message_lines.append(f"Total: ₹{bill.total}")
    text = quote_plus("\n".join(message_lines))

    whatsapp_url = "https://api.whatsapp.com/send"
    if phone:
        whatsapp_url += f"?phone={phone}&text={text}"
    else:
        whatsapp_url += f"?text={text}"

    return redirect(whatsapp_url)

# ---------------- BILLING ----------------
@app.route('/billing', methods=['GET','POST'])
def billing():
    if request.method == 'POST':
        items = request.form.getlist('name')
        qtys = request.form.getlist('qty')
        total = 0

        bill = Bill(total=0)
        db.session.add(bill)
        db.session.commit()

        for i in range(len(items)):
            if int(qtys[i]) > 0:
                service = Service.query.filter_by(name=items[i]).first()
                subtotal = service.price * int(qtys[i])
                total += subtotal

                db.session.add(BillItem(
                    bill_id=bill.id,
                    service_name=items[i],
                    quantity=int(qtys[i]),
                    price=service.price
                ))

                stock = Stock.query.filter_by(name=items[i]).first()
                if stock:
                    stock.quantity -= int(qtys[i])

        bill.total = total
        db.session.commit()

        return redirect(f'/invoice/{bill.id}')

    services = Service.query.all()
    return render_template('billing.html', services=services)

# ---------------- INVOICE ----------------
@app.route('/invoice/<int:id>')
def invoice(id):
    bill = Bill.query.get(id)
    if not bill:
        return redirect(url_for('home'))

    items = BillItem.query.filter_by(bill_id=id).all()
    total_profit = 0
    for item in items:
        service = Service.query.filter_by(name=item.service_name).first()
        if service and service.material:
            stock = Stock.query.filter_by(name=service.material).first()
            cost_price = stock.price if stock else item.price
        else:
            cost_price = item.price
        total_profit += (item.price - cost_price) * item.quantity

    return render_template('invoice.html', bill=bill, items=items, total_profit=total_profit)

@app.route('/invoice/<int:id>/download')
def invoice_download(id):
    bill = Bill.query.get(id)
    if not bill:
        return redirect(url_for('home'))

    items = BillItem.query.filter_by(bill_id=id).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    content = []
    content.append(Paragraph("Rudra Computers Invoice", styles['Title']))

    for item in items:
        content.append(Paragraph(
            f"{item.service_name} x {item.quantity} = ₹{item.price * item.quantity}",
            styles['Normal']
        ))

    content.append(Paragraph(f"Total: ₹{bill.total}", styles['Heading2']))
    doc.build(content)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="invoice.pdf")

# ---------------- STOCK ----------------
@app.route('/stock', methods=['GET','POST'])
def stock():
    if request.method == 'POST':
        db.session.add(Stock(
            name=request.form['name'],
            quantity=int(request.form['quantity']),
            price=float(request.form['price']),
            supplier=request.form['supplier'],
            service_type=request.form.get('service_type', '')
        ))
        db.session.commit()

    search = request.args.get('search','')
    stocks = Stock.query.filter(Stock.name.contains(search)).all()
    service_lookup = {s.name: s for s in Service.query.all()}
    service_types = list(set(s.service_type for s in Stock.query.filter(Stock.service_type != None).all() if s.service_type))
    service_types.sort()

    return render_template('stock.html', stocks=stocks, service_lookup=service_lookup, service_types=service_types)

@app.route('/stock/edit/<int:stock_id>', methods=['GET','POST'])
def edit_stock(stock_id):
    stock = Stock.query.get(stock_id)
    if not stock:
        return redirect(url_for('stock'))
    
    if request.method == 'POST':
        stock.name = request.form['name']
        stock.quantity = int(request.form['quantity'])
        stock.price = float(request.form['price'])
        stock.supplier = request.form['supplier']
        stock.service_type = request.form.get('service_type', '')
        db.session.commit()
        return redirect(url_for('stock'))
    
    service_types = list(set(s.service_type for s in Stock.query.filter(Stock.service_type != None).all() if s.service_type))
    service_types.sort()
    return render_template('edit_stock.html', stock=stock, service_types=service_types)

@app.route('/stock/delete/<int:stock_id>', methods=['POST'])
def delete_stock(stock_id):
    stock = Stock.query.get(stock_id)
    if stock:
        db.session.delete(stock)
        db.session.commit()
    return redirect(url_for('stock'))

# ---------------- REPORTS ----------------
@app.route('/reports')
def reports():
    bills = Bill.query.all()
    total = sum(b.total for b in bills)

    total_profit = 0
    for item in BillItem.query.all():
        service = Service.query.filter_by(name=item.service_name).first()
        if service and service.material:
            stock = Stock.query.filter_by(name=service.material).first()
            cost_price = stock.price if stock else item.price
        else:
            cost_price = item.price
        total_profit += (item.price - cost_price) * item.quantity

    return render_template('reports.html', bills=bills, total=total, total_profit=total_profit)

@app.route('/reports/edit/<int:bill_id>', methods=['GET', 'POST'])
def edit_report(bill_id):
    if 'user' not in session:
        return redirect('/login')

    bill = Bill.query.get(bill_id)
    if not bill:
        return redirect(url_for('reports'))

    items = BillItem.query.filter_by(bill_id=bill_id).all()

    if request.method == 'POST':
        total = 0
        for item in items:
            name = request.form.get(f'name_{item.id}', '').strip()
            try:
                qty = int(request.form.get(f'quantity_{item.id}', item.quantity))
            except ValueError:
                qty = item.quantity
            try:
                price = float(request.form.get(f'price_{item.id}', item.price))
            except ValueError:
                price = item.price

            if name:
                item.service_name = name
            item.quantity = max(qty, 1)
            item.price = max(price, 0)
            total += item.quantity * item.price

        bill.total = total
        db.session.commit()
        return redirect(url_for('reports'))

    return render_template('edit_report.html', bill=bill, items=items)

@app.route('/reports/delete/<int:bill_id>', methods=['POST'])
def delete_report(bill_id):
    if 'user' not in session:
        return redirect('/login')

    bill = Bill.query.get(bill_id)
    if bill:
        BillItem.query.filter_by(bill_id=bill_id).delete()
        db.session.delete(bill)
        db.session.commit()
    return redirect(url_for('reports'))

# ---------------- EXPORT CSV ----------------
@app.route('/export')
def export():
    bills = Bill.query.all()

    data = [{"date": b.date, "total": b.total} for b in bills]
    df = pd.DataFrame(data)

    file = "report.csv"
    df.to_csv(file, index=False)

    return send_file(file, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
