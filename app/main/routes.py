from flask import render_template, request, url_for, redirect
from sqlalchemy import or_, delete
from app.ext import db
from app.main import bp
from app.main.forms import NewNoteForm, ViewNoteForm
from app.models.note import Note
from datetime import datetime








@bp.route('/')
def index():

  form = NewNoteForm()

  # TEMP for displaying all notes
  notes = Note.query.all()


  # Look into the package `Wonderwords` for generating a random passphrase
  # https://pypi.org/project/wonderwords/


  return render_template('index.html', form=form, notes=notes)








@bp.route('/new', methods=['GET', 'POST'])
def new_note():

  form = NewNoteForm()


  if request.method == 'POST' and form.validate():
  
    from app.ext import db

    new_note = Note(
                     content=form.new_note.data,
                     passphrase=form.passphrase.data,
                     expires=form.expires.data
                   )
                   
    db.session.add(new_note)
    db.session.commit()
    
    just_added_note = Note.query.get(new_note.id)
    
    return redirect(url_for('main.secret', slug=just_added_note.slug))

  else:
  
    # Redirect to our error page
    return redirect(url_for('main.bad_note'))








@bp.route('/secret/<string:slug>')
def secret(slug):


  if not isinstance(slug, str) or len(slug) < 5:
  
    return redirect(url_for('main.no_note'))
    
  else:
  
    note = Note.query.filter_by( slug=slug ).first()
    
    if note:
    
      form = ViewNoteForm(request.form, note_slug=slug)
      
      errors = { 'remaining_attempts' : None }
      
      if note.bad_view_count:
        
        num_remaining = 5 - int(note.bad_view_count)
        
        num_remaining_msg = f'{num_remaining} remaining attempt{"" if num_remaining == 1 else "s"}'
      
        errors['remaining_attempts'] = num_remaining_msg
    
      return render_template('secret.html', slug=slug, form=form, errors=errors)
      
    else:
    
      return redirect(url_for('main.no_note'))








@bp.route('/note/<string:slug>', methods=['POST'])
def view_note(slug):

  if not isinstance(slug, str) or len(slug) < 5:
  
    return redirect(url_for('main.no_note'))
    
  else:
  
    note = Note.query.filter_by( slug=slug ).first()
    
    if note:
    
      from config import Config
      from cryptography.fernet import Fernet, InvalidToken
      from app.main.utils import gen_fernet_key
    
      secret = Config.SECRET_KEY
      passphrase = request.form.get('passphrase')
      
      
      if passphrase:
    
        key_seed = secret.join( passphrase )
      
      else:
    
        key_seed = secret
  
  
      key = gen_fernet_key( key_seed )



      # Try to decrypt our note.
      # If the passphrase is incorrect, increment the counter and redirect
      # back to the secret page.
      try:
        
        fernet = Fernet(key)
        decrypted_note = fernet.decrypt( note.content ).decode('utf-8')
    
      except (InvalidToken, TypeError):

        note.bad_view_count += 1
        db.session.commit()

        return redirect( url_for('main.secret', slug=slug) )
      
    
    
      # Render the template, then delete the note.
      try:
      
        return render_template('view-note.html', note=note, decrypted_note=decrypted_note)
      
      finally:
      
        db.session.delete(note)
        db.session.commit()
      
    else:
    
      return redirect( url_for('main.no_note') )








# @internal these two routes could be combined
# to use unique URLs, but the same template
# with the content being passed as a parameter
# and descriptive of why the user got an error.
@bp.route('/no-note')
def no_note():

  return render_template('no-note.html')



@bp.route('/new/error')
def bad_note():

  return render_template('invalid-note.html')








# Before any page request we are going to purge all expired notes.
# @internal This may be excessive. It may be more reasonable to
# only perform this purge when someone is trying to view a note.
@bp.before_request
def purge_old_notes():
  
  current_timestamp = datetime.now()

  # Query to delete rows with expired timestamps
  expired_notes = delete(Note).where(
                                     or_(
                                          Note.expires_at < current_timestamp,  # Expired notes
                                          Note.expires_at.is_(None),            # Notes with null expires_at
                                          Note.bad_view_count >= 5              # Too many bad passphrase attempts
                                        )
                                   )


  # Execute the query
  db.session.execute(expired_notes)
  db.session.commit()









# Handle method not allowed errors.
# The most common reason for this error is a direct hit to the
# view_note route, which only accepts POST requests.
# In those cases we won't know if the note slug is valid, but
# we don't need to.  Just test whether the URL segment looks like
# a slug, and if it does redirect to the secret page. Let that
# route handle the note lookup.
@bp.app_errorhandler(405)
def method_not_allowed(e):

  url_segments = request.path.split('/')
  resource_id = url_segments[2]

  if (
        ( isinstance(resource_id, str) ) and 
        ( 5 <= len(resource_id) <= 20) and
        ( request.path == url_for('main.view_note', slug=resource_id) )
     ):

    return redirect( url_for('main.secret', slug=resource_id) )

  else:

    return redirect( url_for('main.index') )




