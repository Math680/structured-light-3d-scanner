using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using AForge.Video.DirectShow;
using OpenCvSharp;
using OpenCvSharp.Extensions;
using System.IO;
using System.IO.Compression;
using System.Drawing.Imaging;

namespace ProntoUI
{

    
    public partial class Form1 : Form
    {
        private enum CalibrationEtat
        {
            Inactive = 0,
            AttentePhoto2 = 1
        }

        private FilterInfoCollection _videoDevices;
        private VideoCaptureDevice _cam2;
        private VideoCapture _cvCapture;
        private CancellationTokenSource _cvCaptureLoopCts;
        private bool _isPreviewRunning;
        private int _cameraIndex;

        private Bitmap _lastFrame;
        private readonly object _frameLock = new object();
        private bool _framePresentationPending;

        private Process _pythonProcess;
        private int _capturesAttendues;
        private int _capturesEffectuees;
        private bool _acquisitionEnCours;
        private int _triggersEnAttente;
        private bool _traitementTriggerEnCours;
        private int _intervalMs;
        private CalibrationEtat _calibrationEtat = CalibrationEtat.Inactive;
        private Process _damierProcess;
        private string _currentProjectPath;

        private const string ProjectExtension = ".pronto3d";
        private static readonly System.Drawing.Size PreferredPreviewSize = new System.Drawing.Size(1280, 720);


        public Form1()
        {
            InitializeComponent();


            // Important : démarrer/stopper selon l’onglet affiché
            tabControl1.SelectedIndexChanged += TabControl1_SelectedIndexChanged;
            this.FormClosing += Form1_FormClosing;

            // Liste des caméras
            _videoDevices = new FilterInfoCollection(FilterCategory.VideoInputDevice);
            // _videoDevices.Count => nombre de webcams détectées
            UpdateWindowTitle();
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
            if (_isPreviewRunning) return;

            if (_videoDevices == null || _videoDevices.Count == 0)
            {
                MessageBox.Show("Aucune webcam détectée.");
                return;
            }

            _cameraIndex = _videoDevices.Count >= 2 ? 1 : 0;
            _cam2 = new VideoCaptureDevice(_videoDevices[_cameraIndex].MonikerString);

            if (!StartOpenCvPreview())
            {
                MessageBox.Show("Impossible de demarrer la webcam avec OpenCV.");
            }
        }

        private void StopCam2()
        {
            _cvCaptureLoopCts?.Cancel();
            _cvCaptureLoopCts?.Dispose();
            _cvCaptureLoopCts = null;

            if (_cvCapture != null)
            {
                _cvCapture.Release();
                _cvCapture.Dispose();
                _cvCapture = null;
            }

            _cam2 = null;
            _isPreviewRunning = false;

            var old = pictureBox1.Image;
            pictureBox1.Image = null;
            old?.Dispose();

            lock (_frameLock)
            {
                _lastFrame?.Dispose();
                _lastFrame = null;
            }

            _framePresentationPending = false;
        }

        private bool StartOpenCvPreview()
        {
            _cvCaptureLoopCts?.Cancel();
            _cvCaptureLoopCts?.Dispose();
            _cvCaptureLoopCts = new CancellationTokenSource();

            if (TryOpenCapture(VideoCaptureAPIs.DSHOW, out _cvCapture) || TryOpenCapture(VideoCaptureAPIs.MSMF, out _cvCapture))
            {
                _isPreviewRunning = true;
                StartPreviewLoop(_cvCaptureLoopCts.Token);
                return true;
            }

            _cvCapture = null;
            _isPreviewRunning = false;
            return false;
        }

        private bool TryOpenCapture(VideoCaptureAPIs api, out VideoCapture capture)
        {
            capture = new VideoCapture(_cameraIndex, api);
            if (!capture.IsOpened())
            {
                capture.Dispose();
                capture = null;
                return false;
            }

            capture.Set(VideoCaptureProperties.FourCC, FourCC.MJPG);
            capture.Set(VideoCaptureProperties.FrameWidth, PreferredPreviewSize.Width);
            capture.Set(VideoCaptureProperties.FrameHeight, PreferredPreviewSize.Height);
            capture.Set(VideoCaptureProperties.Fps, 30);
            capture.Set(VideoCaptureProperties.BufferSize, 1);
            capture.Set(VideoCaptureProperties.ConvertRgb, 1);
            return true;
        }

        private void StartPreviewLoop(CancellationToken token)
        {
            _ = Task.Run(() =>
            {
                using (var frame = new Mat())
                {
                    while (!token.IsCancellationRequested && _cvCapture != null && _cvCapture.IsOpened())
                    {
                        if (!_cvCapture.Read(frame) || frame.Empty())
                        {
                            Thread.Sleep(10);
                            continue;
                        }

                        using (Bitmap bitmap = BitmapConverter.ToBitmap(frame))
                        {
                            lock (_frameLock)
                            {
                                _lastFrame?.Dispose();
                                _lastFrame = (Bitmap)bitmap.Clone();
                            }

                            if (!pictureBox1.IsHandleCreated || _framePresentationPending)
                            {
                                continue;
                            }

                            Bitmap uiBitmap = (Bitmap)bitmap.Clone();
                            _framePresentationPending = true;

                            try
                            {
                                pictureBox1.BeginInvoke(new Action(() =>
                                {
                                    try
                                    {
                                        var old = pictureBox1.Image;
                                        pictureBox1.Image = uiBitmap;
                                        old?.Dispose();
                                    }
                                    finally
                                    {
                                        _framePresentationPending = false;
                                    }
                                }));
                            }
                            catch
                            {
                                uiBitmap.Dispose();
                                _framePresentationPending = false;
                                return;
                            }
                        }
                    }
                }
            }, token);
        }

        private void Form1_FormClosing(object sender, FormClosingEventArgs e)
        {
            TerminerAcquisition();
            TerminerProjectionDamier();
            StopCam2();
        }

        private void label2_Click(object sender, EventArgs e)
        {

        }

        private void label1_Click(object sender, EventArgs e)
        {

        }

        private void nouveauProjetToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if (MessageBox.Show("Reinitialiser le projet courant et supprimer les captures locales non enregistrees ?", "Nouveau projet", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            {
                return;
            }

            ResetLocalProjectData();
            _currentProjectPath = null;
            _calibrationEtat = CalibrationEtat.Inactive;
            button3.Text = "Calibration";
            label1.Text = "Nouveau projet cree";
            UpdateWindowTitle();
        }

        private void ouvrirToolStripMenuItem_Click(object sender, EventArgs e)
        {
            using (var dialog = new OpenFileDialog())
            {
                dialog.Filter = $"Projet Pronto (*{ProjectExtension})|*{ProjectExtension}";
                dialog.Title = "Ouvrir un projet";

                if (dialog.ShowDialog(this) != DialogResult.OK)
                {
                    return;
                }

                OuvrirProjet(dialog.FileName);
            }
        }

        private void enregistrerToolStripMenuItem_Click(object sender, EventArgs e)
        {
            EnregistrerProjet(false);
        }

        private void enregistrerSousToolStripMenuItem_Click(object sender, EventArgs e)
        {
            EnregistrerProjet(true);
        }

        private void quitterToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Close();
        }

        private void parametresWebcamToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if (!EnsureCameraReady())
            {
                MessageBox.Show(this, "Webcam indisponible.", "Parametres webcam", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            try
            {
                _cam2.DisplayPropertyPage(Handle);
            }
            catch (NotSupportedException)
            {
                MessageBox.Show(this, "Cette webcam ne fournit pas de page de proprietes via le driver DirectShow.", "Parametres webcam", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"Impossible d'ouvrir les parametres webcam : {ex.Message}", "Parametres webcam", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void button3_Click(object sender, EventArgs e)
        {
            if (_acquisitionEnCours)
            {
                label1.Text = "Arreter l'acquisition avant la calibration";
                return;
            }

            if (!EnsureCameraReady())
            {
                label1.Text = "Webcam indisponible pour la calibration";
                return;
            }

            switch (_calibrationEtat)
            {
                case CalibrationEtat.Inactive:
                    if (!LancerProjectionDamier())
                    {
                        label1.Text = "Projection damier indisponible";
                        return;
                    }

                    if (!SauvegarderCaptureCalibration(1))
                    {
                        label1.Text = "Impossible de prendre la photo 1";
                        return;
                    }

                    _calibrationEtat = CalibrationEtat.AttentePhoto2;
                    button3.Text = "Calibration - Photo 2";
                    label1.Text = "Calibration: photo 1 enregistree, deplacer le plan puis reprendre";
                    break;

                case CalibrationEtat.AttentePhoto2:
                    if (!SauvegarderCaptureCalibration(2))
                    {
                        label1.Text = "Impossible de prendre la photo 2";
                        return;
                    }

                    TerminerProjectionDamier();
                    _calibrationEtat = CalibrationEtat.Inactive;
                    button3.Text = "Calibration";
                    label1.Text = "Calibration terminee: 2 photos enregistrees";
                    break;
            }
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
            if (_isPreviewRunning)
            {
                return true;
            }

            StartCam2();
            return _isPreviewRunning;
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

        private bool SauvegarderCaptureCalibration(int indexCapture)
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
                string dossier = Path.Combine(Application.StartupPath, "captures", "calibration_emetteur");
                Directory.CreateDirectory(dossier);

                string nomFichier = $"capture_calibration_{indexCapture}.png";
                string cheminComplet = Path.Combine(dossier, nomFichier);

                imageASauver.Save(cheminComplet, ImageFormat.Png);
                return true;
            }
            finally
            {
                imageASauver.Dispose();
            }
        }

        private bool LancerProjectionDamier()
        {
            if (_damierProcess != null && !_damierProcess.HasExited)
            {
                return true;
            }

            string scriptPath = Path.Combine(Application.StartupPath, "prgm", "damier_fullscreen.py");
            if (!File.Exists(scriptPath))
            {
                return false;
            }

            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "python",
                    Arguments = "prgm/damier_fullscreen.py",
                    UseShellExecute = false,
                    RedirectStandardOutput = false,
                    RedirectStandardError = false,
                    CreateNoWindow = true,
                    WorkingDirectory = Application.StartupPath
                };

                _damierProcess = new Process();
                _damierProcess.StartInfo = psi;
                _damierProcess.Start();
                return true;
            }
            catch
            {
                _damierProcess = null;
                return false;
            }
        }

        private void TerminerProjectionDamier()
        {
            if (_damierProcess == null)
            {
                return;
            }

            try
            {
                if (!_damierProcess.HasExited)
                {
                    _damierProcess.Kill();
                }
            }
            catch
            {
            }
            finally
            {
                _damierProcess.Dispose();
                _damierProcess = null;
            }
        }

        private string GetCapturesRoot()
        {
            return Path.Combine(Application.StartupPath, "captures");
        }

        private string GetMetadataFilePath()
        {
            return Path.Combine(Application.StartupPath, "project_metadata.txt");
        }

        private void ResetLocalProjectData()
        {
            string capturesRoot = GetCapturesRoot();
            if (Directory.Exists(capturesRoot))
            {
                Directory.Delete(capturesRoot, true);
            }

            string metadataPath = GetMetadataFilePath();
            if (File.Exists(metadataPath))
            {
                File.Delete(metadataPath);
            }
        }

        private void UpdateWindowTitle()
        {
            string projectName = string.IsNullOrWhiteSpace(_currentProjectPath)
                ? "Projet non enregistre"
                : Path.GetFileNameWithoutExtension(_currentProjectPath);

            Text = $"Imageur 3D | Pronto | {projectName}";
        }

        private void WriteProjectMetadata(string tempDirectory)
        {
            string metadataPath = Path.Combine(tempDirectory, "project_metadata.txt");
            var lines = new[]
            {
                $"TrackBarN={trackBar1.Value}",
                $"Contraste={trackBar2.Value}",
                $"CalibrationEtat={(int)_calibrationEtat}"
            };
            File.WriteAllLines(metadataPath, lines);
        }

        private void ReadProjectMetadata(string extractedDirectory)
        {
            string metadataPath = Path.Combine(extractedDirectory, "project_metadata.txt");
            if (!File.Exists(metadataPath))
            {
                return;
            }

            foreach (string line in File.ReadAllLines(metadataPath))
            {
                string[] parts = line.Split('=');
                if (parts.Length != 2)
                {
                    continue;
                }

                if (parts[0] == "TrackBarN" && int.TryParse(parts[1], out int trackN))
                {
                    trackBar1.Value = Math.Max(trackBar1.Minimum, Math.Min(trackBar1.Maximum, trackN));
                    label1.Text = "N = " + trackBar1.Value;
                }
                else if (parts[0] == "Contraste" && int.TryParse(parts[1], out int contrast))
                {
                    trackBar2.Value = Math.Max(trackBar2.Minimum, Math.Min(trackBar2.Maximum, contrast));
                    label2.Text = "Contraste : " + trackBar2.Value;
                }
            }
        }

        private void EnregistrerProjet(bool forceSaveAs)
        {
            string targetPath = _currentProjectPath;

            if (forceSaveAs || string.IsNullOrWhiteSpace(targetPath))
            {
                using (var dialog = new SaveFileDialog())
                {
                    dialog.Filter = $"Projet Pronto (*{ProjectExtension})|*{ProjectExtension}";
                    dialog.Title = "Enregistrer le projet";
                    dialog.DefaultExt = ProjectExtension.TrimStart('.');
                    dialog.AddExtension = true;

                    if (dialog.ShowDialog(this) != DialogResult.OK)
                    {
                        return;
                    }

                    targetPath = dialog.FileName;
                }
            }

            if (!targetPath.EndsWith(ProjectExtension, StringComparison.OrdinalIgnoreCase))
            {
                targetPath += ProjectExtension;
            }

            string tempDirectory = Path.Combine(Path.GetTempPath(), "ProntoProject_" + Guid.NewGuid().ToString("N"));

            try
            {
                Directory.CreateDirectory(tempDirectory);

                string capturesRoot = GetCapturesRoot();
                if (Directory.Exists(capturesRoot))
                {
                    CopyDirectory(capturesRoot, Path.Combine(tempDirectory, "captures"));
                }

                WriteProjectMetadata(tempDirectory);

                if (File.Exists(targetPath))
                {
                    File.Delete(targetPath);
                }

                ZipFile.CreateFromDirectory(tempDirectory, targetPath, CompressionLevel.Optimal, false);
                _currentProjectPath = targetPath;
                UpdateWindowTitle();
                label1.Text = $"Projet enregistre : {Path.GetFileName(targetPath)}";
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"Impossible d'enregistrer le projet : {ex.Message}", "Enregistrement", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                if (Directory.Exists(tempDirectory))
                {
                    Directory.Delete(tempDirectory, true);
                }
            }
        }

        private void OuvrirProjet(string projectPath)
        {
            string tempDirectory = Path.Combine(Path.GetTempPath(), "ProntoProject_" + Guid.NewGuid().ToString("N"));

            try
            {
                Directory.CreateDirectory(tempDirectory);
                ZipFile.ExtractToDirectory(projectPath, tempDirectory);

                ResetLocalProjectData();

                string extractedCaptures = Path.Combine(tempDirectory, "captures");
                if (Directory.Exists(extractedCaptures))
                {
                    CopyDirectory(extractedCaptures, GetCapturesRoot());
                }

                ReadProjectMetadata(tempDirectory);
                _currentProjectPath = projectPath;
                _calibrationEtat = CalibrationEtat.Inactive;
                button3.Text = "Calibration";
                UpdateWindowTitle();
                label1.Text = $"Projet ouvert : {Path.GetFileName(projectPath)}";
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"Impossible d'ouvrir le projet : {ex.Message}", "Ouverture", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                if (Directory.Exists(tempDirectory))
                {
                    Directory.Delete(tempDirectory, true);
                }
            }
        }

        private void CopyDirectory(string sourceDirectory, string targetDirectory)
        {
            Directory.CreateDirectory(targetDirectory);

            foreach (string file in Directory.GetFiles(sourceDirectory))
            {
                string targetFile = Path.Combine(targetDirectory, Path.GetFileName(file));
                File.Copy(file, targetFile, true);
            }

            foreach (string directory in Directory.GetDirectories(sourceDirectory))
            {
                string targetSubDirectory = Path.Combine(targetDirectory, Path.GetFileName(directory));
                CopyDirectory(directory, targetSubDirectory);
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
