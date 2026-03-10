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

namespace ProntoUI
{

    
    public partial class Form1 : Form
    {
        private FilterInfoCollection _videoDevices;
        private VideoCaptureDevice _cam2;

        private Bitmap _lastFrame;
        private readonly object _frameLock = new object();

        private Process _pythonProcess;


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

        private async void button1_Click(object sender, EventArgs e)
        {
            int delaySeconds = 3000; // par exemple

            var psi = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = "prgm/franges_fullscreen.py " + trackBar1.Value + " " + delaySeconds,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            _pythonProcess = new Process();
            _pythonProcess.StartInfo = psi;

            //_pythonProcess.OutputDataReceived += Python_OutputDataReceived;
            //_pythonProcess.ErrorDataReceived += Python_ErrorDataReceived;

            _pythonProcess.Start();
            _pythonProcess.BeginOutputReadLine();
            _pythonProcess.BeginErrorReadLine();


            await Task.Delay(1500);


            for (int i = 0; i < trackBar1.Value; i++)
            {
                Bitmap imageASauver = null;

                lock (_frameLock)
                {
                    if (_lastFrame != null)
                        imageASauver = (Bitmap)_lastFrame.Clone();
                }

                if (imageASauver == null)
                {
                    MessageBox.Show("Aucune image disponible.");
                    return;
                }

                try
                {
                    string dossier = Path.Combine(Application.StartupPath, "captures", "1");
                    Directory.CreateDirectory(dossier);


                    string nomFichier = $"capture_{i+1}.png";
                    string cheminComplet = Path.Combine(dossier, nomFichier);

                    imageASauver.Save(cheminComplet, System.Drawing.Imaging.ImageFormat.Png);

                    
                }
                finally
                {
                    imageASauver.Dispose();
                }


                await Task.Delay(delaySeconds);

            }

            if (_pythonProcess != null && !_pythonProcess.HasExited)
            {
                _pythonProcess.Kill();
            }
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

            if (_videoDevices == null || _videoDevices.Count < 2)
            {
                MessageBox.Show("Moins de 2 webcams détectées.");
                return;
            }

            // 2e webcam = index 1
            _cam2 = new VideoCaptureDevice(_videoDevices[1].MonikerString);

            // Optionnel : choisir une résolution (sinon la valeur par défaut)
            // var caps = _cam2.VideoCapabilities;
            // _cam2.VideoResolution = caps[0];

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
    }
}
