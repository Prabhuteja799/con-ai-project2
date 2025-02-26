from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, send_from_directory, flash
import os
from google.cloud import speech, texttospeech_v1, language_v2
from google.protobuf import wrappers_pb2

app = Flask(__name__)

# Configure upload folders
UPLOAD_FOLDER = 'uploads'
TTS_FOLDER = 'tts'
ALLOWED_EXTENSIONS = {'wav'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TTS_FOLDER'] = TTS_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TTS_FOLDER, exist_ok=True)

# Google Cloud Speech-to-Text Client
speech_client = speech.SpeechClient()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_files():
    files = []
    for filename in os.listdir(UPLOAD_FOLDER):
        if allowed_file(filename):
            files.append(filename)
    files.sort(reverse=True)
    return files

def sample_recognize(content):
    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        language_code="en-US",
        model="latest_long",
        audio_channel_count=1,
        enable_word_confidence=True,
        enable_word_time_offsets=True,
    )
    operation = speech_client.long_running_recognize(config=config, audio=audio)
    response = operation.result(timeout=90)
    
    txt = ''
    for result in response.results:
        txt += result.alternatives[0].transcript + '\n'
    
    return txt

# Google Cloud Text-to-Speech Client
texttospeech_client = texttospeech_v1.TextToSpeechClient()

def sample_synthesize_speech(text=None, ssml=None):
    input = texttospeech_v1.SynthesisInput()
    if ssml:
        input.ssml = ssml
    else:
        input.text = text

    voice = texttospeech_v1.VoiceSelectionParams(language_code="en-UK")
    audio_config = texttospeech_v1.AudioConfig(audio_encoding="LINEAR16")

    request = texttospeech_v1.SynthesizeSpeechRequest(
        input=input,
        voice=voice,
        audio_config=audio_config,
    )
    response = texttospeech_client.synthesize_speech(request=request)
    return response.audio_content

# Google Cloud Natural Language API: Sentiment Analysis
def sample_analyze_sentiment(text_content: str):
    client = language_v2.LanguageServiceClient()
    document_type_in_plain_text = language_v2.Document.Type.PLAIN_TEXT
    language_code = "en"
    document = {
        "content": text_content,
        "type_": document_type_in_plain_text,
        "language_code": language_code,
    }
    encoding_type = language_v2.EncodingType.UTF8

    response = client.analyze_sentiment(
        request={"document": document, "encoding_type": encoding_type}
    )
    return response

@app.route('/')
def index():
    files = get_files()
    tts_files = os.listdir(app.config['TTS_FOLDER'])
    return render_template('index.html', files=files, tts_files=tts_files)

@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'audio_data' not in request.files:
        flash('No audio data')
        return redirect(request.url)
    file = request.files['audio_data']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        # Save the audio file
        filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Transcribe audio using Speech-to-Text
        with open(file_path, 'rb') as f:
            content = f.read()
        transcript = sample_recognize(content)

        # Perform sentiment analysis on the transcript
        sentiment_response = sample_analyze_sentiment(transcript)
        score = sentiment_response.document_sentiment.score * sentiment_response.document_sentiment.magnitude
        if score > 0.75:
            sentiment_label = "POSITIVE"
        elif score < -0.75:
            sentiment_label = "NEGATIVE"
        else:
            sentiment_label = "NEUTRAL"

        # Save the transcript along with sentiment results
        transcript_path = file_path + '.txt'
        with open(transcript_path, 'w') as f:
            f.write("TRANSCRIPT:\n")
            f.write(transcript)
            f.write("\n\nSENTIMENT ANALYSIS:\n")
            f.write(f"Score: {sentiment_response.document_sentiment.score}\n")
            f.write(f"Magnitude: {sentiment_response.document_sentiment.magnitude}\n")
            f.write(f"Overall sentiment: {sentiment_label}\n")
            # Optionally, include a visualization link if you add a viewer page
            # f.write("Visualization link: <insert_link_here>\n")

    return redirect('/')

@app.route('/upload/<filename>')
def get_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

@app.route('/upload_text', methods=['POST'])
def upload_text():
    text = request.form['text']
    if text:
        # Perform sentiment analysis on the input text
        sentiment_response = sample_analyze_sentiment(text)
        score = sentiment_response.document_sentiment.score * sentiment_response.document_sentiment.magnitude
        if score > 0.75:
            sentiment_label = "POSITIVE"
        elif score < -0.75:
            sentiment_label = "NEGATIVE"
        else:
            sentiment_label = "NEUTRAL"

        # Combine the original text with sentiment analysis results
        combined_text = (
            f"Original Text: {text}\n\n"
            "Sentiment Analysis:\n"
            f"Score: {sentiment_response.document_sentiment.score}\n"
            f"Magnitude: {sentiment_response.document_sentiment.magnitude}\n"
            f"Overall Sentiment: {sentiment_label}"
        )

        # Generate a unique filename and path
        filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
        tts_path = os.path.join(app.config['TTS_FOLDER'], filename)

        # Generate speech from the combined text
        audio_content = sample_synthesize_speech(text=text)

        # Save the generated audio
        with open(tts_path, 'wb') as f:
            f.write(audio_content)

        # Save the text transcript along with sentiment analysis results
        transcript_txt_path = tts_path + '.txt'
        with open(transcript_txt_path, 'w') as f:
            f.write(combined_text)


    return redirect('/')



# Serve TTS files (audio and transcript)
@app.route('/tts/<filename>')
def tts_file(filename):
    return send_from_directory(app.config['TTS_FOLDER'], filename)

@app.route('/script.js', methods=['GET'])
def scripts_js():
    return send_file('./script.js')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)



if __name__ == '__main__':
    app.run(debug=True)
