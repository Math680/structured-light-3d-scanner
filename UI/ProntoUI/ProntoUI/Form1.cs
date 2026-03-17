using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Windows.Forms;
using AForge.Video;
using AForge.Video.DirectShow;
using System.IO;
using System.Drawing.Imaging;

namespace ProntoUI
{

    
    public partial class Form1 : Form
    {
        private FilterInfoCollection _videoDevices;
        private VideoCaptureDevice _cam2;

        private Bitmap _lastFrame;
        private readonly object _frameLock = new object();

        private Process _pythonProcess;
        private int _capturesAttendues;
        private int _capturesEffectuees;
        private bool _acquisitionEnCours;
        private int _triggersEnAttente;
        private bool _traitementTriggerEnCours;
        private int _intervalMs;


        public Form1()
        {
            InitializeComponent();


            // Important : démarrer/stopper selon l’onglet affiché
            tabControl1.SelectedIndexChanged += TabControl1_SelectedIndexChanged;
            this.FormClosing += Form1_FormClosing;

            // Liste des caméras
            _videoDevices = new FilterInfoCollection(FilterCategory.VideoInputDevice);
            // _videoDevices.Count => nombre de webcams détectées
        }

        private void button1_Click(object sender, EventArgs e)
        {
            if (_acquisitionEnCours)
            {
                return;
            }

            if (!EnsureCameraReady())
            {
                return;
            }

            _intervalMs = 2000;
            _capturesAttendues = trackBar1.Value;
            _capturesEffectuees = 0;
            _acquisitionEnCours = true;
            label1.Text = $"Acquisition en cours (0/{_capturesAttendues})";

            var psi = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = "prgm/franges_fullscreen.py " + trackBar1.Value + " " + _intervalMs,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            _pythonProcess = new Process();
            _pythonProcess.StartInfo = psi;

            _pythonProcess.OutputDataReceived += Python_OutputDataReceived;
            _pythonProcess.ErrorDataReceived += Python_ErrorDataReceived;

            _pythonProcess.Start();
            _pythonProcess.BeginOutputReadLine();
            _pythonProcess.BeginErrorReadLine();
        }

        private void trackBar1_Scroll(object sender, EventArgs e)
        {
            label1.Text = "N = " + (trackBar1.Value);
        }

        private void trackBar2_Scroll(object sender, EventArgs e)
        {
            label2.Text = "Contraste : " + trackBar2.Value;

        }

        private void pictureBox1_Click(object sender, EventArgs e)
        {

        }


        private void TabControl1_SelectedIndexChanged(object sender, EventArgs e)
        {
            // Si on va sur l’onglet 2, on démarre la cam2, sinon on stop
            if (tabControl1.SelectedTab == tabPage2)
                StartCam2();
            else
                StopCam2();
        }


        private void StartCam2()
        {
            if (_cam2 != null && _cam2.IsRunning) return;

            if (_videoDevices == null || _videoDevices.Count == 0)
            {
                MessageBox.Show("Aucune webcam détectée.");
                return;
            }

            int cameraIndex = _videoDevices.Count >= 2 ? 1 : 0;
            _cam2 = new VideoCaptureDevice(_videoDevices[cameraIndex].MonikerString);

            var caps = _cam2.VideoCapabilities;
            if (caps != null && caps.Length > 0)
            {
                _cam2.VideoResolution = caps
                    .OrderByDescending(c => c.FrameSize.Width * c.FrameSize.Height)
                    .First();
            }

            _cam2.NewFrame += Cam2_NewFrame;
            _cam2.Start();
        }

        private void Cam2_NewFrame(object sender, NewFrameEventArgs eventArgs)
        {
            // Clone de la frame reçue
            Bitmap frame = (Bitmap)eventArgs.Frame.Clone();

            // On stocke une copie pour pouvoir l'enregistrer plus tard
            lock (_frameLock)
            {
                _lastFrame?.Dispose();
                _lastFrame = (Bitmap)frame.Clone();
            }

            // Mise à jour UI
            if (pictureBox1.IsHandleCreated)
            {
                pictureBox1.BeginInvoke(new Action(() =>
                {
                    var old = pictureBox1.Image;
                    pictureBox1.Image = frame;
                    old?.Dispose();
                }));
            }
            else
            {
                frame.Dispose();
            }
        }

        private void StopCam2()
        {
            if (_cam2 == null) return;

            if (_cam2.IsRunning)
            {
                _cam2.NewFrame -= Cam2_NewFrame;
                _cam2.SignalToStop();
                _cam2.WaitForStop();
            }

            _cam2 = null;

            var old = pictureBox1.Image;
            pictureBox1.Image = null;
            old?.Dispose();

            lock (_frameLock)
            {
                _lastFrame?.Dispose();
                _lastFrame = null;
            }
        }

        private void Form1_FormClosing(object sender, FormClosingEventArgs e)
        {
            TerminerAcquisition();
            StopCam2();
        }

        private void label2_Click(object sender, EventArgs e)
        {

        }

        private void label1_Click(object sender, EventArgs e)
        {

        }

        private void button3_Click(object sender, EventArgs e)
        {

        }


        private void Python_OutputDataReceived(object sender, DataReceivedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(e.Data))
                return;

            string message = e.Data.Trim();

            BeginInvoke(new Action(() =>
            {
                if (message.StartsWith("PHOTO_TRIGGER"))
                {
                    _triggersEnAttente++;
                    _ = TraiterTriggersCaptureAsync();
                }
            }));
        }

        private void Python_ErrorDataReceived(object sender, DataReceivedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(e.Data))
                return;

            
        }

        private void FaireActionCSharp()
        {
            // Ton action C#
            label1.Text = "Action déclenchée par Python";
        }

        private bool EnsureCameraReady()
        {
            if (_cam2 != null && _cam2.IsRunning)
            {
                return true;
            }

            StartCam2();
            return _cam2 != null && _cam2.IsRunning;
        }

        private async Task TraiterTriggersCaptureAsync()
        {
            if (_traitementTriggerEnCours)
            {
                return;
            }

            _traitementTriggerEnCours = true;

            try
            {
                while (_acquisitionEnCours && _capturesEffectuees < _capturesAttendues && _triggersEnAttente > 0)
                {
                    _triggersEnAttente--;
                    await Task.Delay(Math.Max(1, _intervalMs / 2));

                    bool captureSauvegardee = false;
                    for (int tentative = 0; tentative < 5 && !captureSauvegardee; tentative++)
                    {
                        captureSauvegardee = SauvegarderFrameCourante(_capturesEffectuees + 1);
                        if (!captureSauvegardee)
                        {
                            await Task.Delay(100);
                        }
                    }

                    if (captureSauvegardee)
                    {
                        _capturesEffectuees++;
                        label1.Text = $"Acquisition en cours ({_capturesEffectuees}/{_capturesAttendues})";
                    }
                    else
                    {
                        label1.Text = "Aucune image webcam disponible";
                    }

                    if (_capturesEffectuees >= _capturesAttendues)
                    {
                        TerminerAcquisition();
                    }
                }
            }
            finally
            {
                _traitementTriggerEnCours = false;
            }
        }

        private bool SauvegarderFrameCourante(int indexCapture)
        {
            Bitmap imageASauver = null;

            lock (_frameLock)
            {
                if (_lastFrame != null)
                {
                    imageASauver = (Bitmap)_lastFrame.Clone();
                }
            }

            if (imageASauver == null)
            {
                return false;
            }

            try
            {
                string dossier = Path.Combine(Application.StartupPath, "captures", "1");
                Directory.CreateDirectory(dossier);

                string nomFichier = $"capture_{indexCapture}.png";
                string cheminComplet = Path.Combine(dossier, nomFichier);

                imageASauver.Save(cheminComplet, ImageFormat.Png);
                return true;
            }
            finally
            {
                imageASauver.Dispose();
            }
        }

        private void TerminerAcquisition()
        {
            _acquisitionEnCours = false;
            _triggersEnAttente = 0;

            if (_pythonProcess != null)
            {
                try
                {
                    if (!_pythonProcess.HasExited)
                    {
                        _pythonProcess.Kill();
                    }
                }
                catch
                {
                }
                finally
                {
                    _pythonProcess.Dispose();
                    _pythonProcess = null;
                }
            }

            label1.Text = $"Acquisition terminée ({_capturesEffectuees}/{_capturesAttendues})";
        }

    }
}
