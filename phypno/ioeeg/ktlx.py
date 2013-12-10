"""Module reads and writes header and data for KTLX data. The files are:
  - .eeg (patient information)
  - .ent (notes, sometimes with a backup file called .ent.old)
  - .erd (raw data)
  - .etc (table of content)
  - .snc (synchronization file)
  - .stc (segmented table of content)
  - .vtc (video table of content)
  - .avi (videos)

There is only one of these files in the directory, except for .erd, .etc., .avi
These files are numbered in the format _%03d, except for the first one, which
is not _000 but there is no extension, for backwards compatibility.

This module contains functions to read each of the files, the files are called
_read_EXT where EXT is one of the extensions.

TODO: check all the times, if they are 1. internally consistent and 2.
meaningful. Absolute time is stored in the header of all the files, and in
.snc. In addition, check the 'start_stamp' in .erd does not start at zero.

"""
from __future__ import division
from binascii import hexlify
from datetime import timedelta, datetime
from glob import glob
from math import ceil
from numpy import zeros
from os import SEEK_END
from os.path import basename, join, exists, splitext
from re import sub, match
from struct import unpack


BITS_IN_BYTE = 8
# http://support.microsoft.com/kb/167296
# How To Convert a UNIX time_t to a Win32 FILETIME or SYSTEMTIME
EPOCH_AS_FILETIME = 116444736000000000  # January 1, 1970 as MS file time
HUNDREDS_OF_NANOSECONDS = 10000000

ZERO = timedelta(0)
HOUR = timedelta(hours=1)


def _calculate_conversion(hdr):
    """Calculate the conversion factor.

    Returns
    -------
    conv_factor : int
        conversion factor (TODO: maybe it's best if it's a vector)

    Notes
    -----
    The conversion factor to engineering units is variable, dependent upon
    headbox_type and m_headbox_sw_version, and which physical channel number is
    being examined.

    Something along the lines of:
    hdr['gain'] = (8711. / (2 ** 21 - 0.5)) * 2 ** hdr['discardbits']

    """
    return 1


def _filetime_to_dt(ft):
    """Converts a Microsoft filetime number to a Python datetime. The new
    datetime object is time zone-naive but is equivalent to tzinfo=utc.

    """
    # Get seconds and remainder in terms of Unix epoch
    s, ns100 = divmod(ft - EPOCH_AS_FILETIME, HUNDREDS_OF_NANOSECONDS)
    # Convert to datetime object
    dt = datetime.utcfromtimestamp(s)
    # Add remainder in as microseconds. Python 3.2 requires an integer
    dt = dt.replace(microsecond=(ns100 // 10))
    return dt


def _make_str(t):
    t = t[:t.index('\x00')]
    return ''.join(t)


def _read_eeg(eeg_file):
    """Reads eeg file, but it doesn't work, the data is in text format, but
    based on Excel. You can read it from the editor, there are still a couple
    of signs that are not in Unicode.

    TODO: parse the text of EEG, if it's interesting

    Notes
    -----
    The patient information file consists of a single null terminated string
    following the generic file header. The string encodes all the patient
    information in a list format defined by a hierarchy of name value pairs.

    """
    pass


def _read_ent(ent_file):
    with open(ent_file, 'r') as f:
        f.seek(352)  # end of header

        note_hdr_length = 16

        allnote = []
        while True:
            note = {}
            note['type'], = unpack('i', f.read(4))
            note['length'], = unpack('i', f.read(4))
            note['prev_length'], = unpack('i', f.read(4))
            note['unused'], = unpack('i', f.read(4))
            if not note['type']:
                break
            s = f.read(note['length'] - note_hdr_length)
            s = s[:-2]  # it ends with one empty byte
            try:
                s1 = s.replace('\n', ' ')
                s1 = s1.replace('\\xd ', '')
                s1 = s1.replace('(.', '{')
                s1 = s1.replace(')', '}')
                s1 = s1.replace('",', '" :')
                s1 = s1.replace('{"', '"')
                s1 = s1.replace('},', ',')
                s1 = s1.replace('}}', '}')
                s1 = sub(r'\(([0-9 ,-\.]*)\}', r'[\1]', s1)
                note['value'] = eval(s1)
                allnote.append(note)
            except:
                pass
    return allnote


def _read_erd(erd_file, n_samples):
    """Read the raw data and return a matrix, no conversion to real units.

    Parameters
    ----------
    erd_file : str
        one of the .erd files to read
    n_samples : int
        the number of samples to read, based on .stc

    Returns
    -------
    data : numpy.ndarray
        2d matrix with the data, as read from the file

    Notes
    -----
    Each sample point consists of these parts:
      - Event Byte
      - Frequency byte (only if file_schema >= 8 and one chan has != freq)
      - Delta mask (only if file_schema >= 8)
      - Delta Information
      - Absolute Channel Values


    Event Byte:
      Bit 0 of the event byte indicates the presence of the external trigger
      during the sample period. It's very rare.

    Delta Mask:
      Bit-mask of a size int( number_of_channels / 8 + 0.5). Each 1 in the mask
      indicates that corresponding channel has 2*n bit delta, 0 means that
      corresponding channel has n bit delta.
      The rest of the byte of the delta mask is filled with "1".
      If file_schema <= 7, it generates a "fake" delta, where everything is 0.

    """
    hdr = _read_hdr_file(erd_file)
    n_chan = hdr['num_channels']
    l_deltamask = int(ceil(n_chan / BITS_IN_BYTE + 0.5))  # deltamask length

    # read single bits as they appear, one by one
    read_bits = lambda x: bin(int(x, 16))[2:].zfill(BITS_IN_BYTE)[::-1]

    with open(erd_file, 'r') as f:
        if hdr['file_schema'] in (7,):
            f.seek(4560)
            abs_delta = '\x80'  # one byte: 10000000

        if hdr['file_schema'] in (8, 9):
            f.seek(8656)
            abs_delta = '\xff\xff'

        output = zeros((n_chan, n_samples))

        for i in range(n_samples):

            # Event Byte
            eventbite = f.read(1)
            if eventbite == '':
                break
            assert hexlify(eventbite) == '00'

            # Delta Information
            if hdr['file_schema'] in (7,):
                deltamask = '0' * n_chan

            if hdr['file_schema'] in (8, 9):
                # TODO: convert using bitwise operations
                hx_deltamask = hexlify(f.read(l_deltamask))  # deltamask as hex
                deltamask = ''
                for v1, v2 in zip(hx_deltamask[::2], hx_deltamask[1::2]):
                    deltamask += read_bits(v1 + v2)

            c = []  # TODO: transform this in bool list
            for i_c, m in enumerate(deltamask[:n_chan]):
                if m == '1':
                    s = f.read(2)
                elif m == '0':
                    s = f.read(1)

                if s == abs_delta:
                    c.append(True)  # read the full value below
                else:
                    c.append(False)  # read only the difference
                    if m == '1':
                        output[i_c, i] = output[i_c, i - 1] + unpack('h', s)[0]
                    elif m == '0':
                        output[i_c, i] = output[i_c, i - 1] + unpack('b', s)[0]

            for i_c in range(n_chan):
                if c[i_c]:
                    s = f.read(4)  # read the full value
                    output[i_c, i] = unpack('i', s)[0]

    return output


def _read_etc(etc_file):
    """Return information about etc.

    ETC contains only 4 4-bytes, I cannot make sense of it. The EEG file format
    does not have an explanation for ETC, it says it's similar to the end of
    STC, which has 4 int, but the values don't match.

    """
    with open(etc_file, 'rb') as f:
        f.seek(352)  # end of header
        v1 = unpack('i', f.read(4))[0]
        v2 = unpack('i', f.read(4))[0]
        v3 = unpack('i', f.read(4))[0]  # always zero?
        v4_a = unpack('h', f.read(2))[0]  # they look like two values
        v4_b = unpack('h', f.read(2))[0]  # maybe this one is unsigned (H)

        f.seek(352)  # end of header
        print(hexlify(f.read(16)))
    return v1, v2, v3, (v4_a, v4_b)


def _read_snc(snc_file):
    """Read Synchronization File and return sample stamp and time

    Returns
    -------
    sampleStamp : list of int
        Sample number from start of study
    sampleTime : list of datetime.datetime
        File time representation of sampleStamp

    Notes
    -----
    TODO: check if the timing is accurate

    The synchronization file is used to calculate a FILETIME given a sample
    stamp (and vise-versa). Theoretically, it is possible to calculate a sample
    stamp's FILETIME given the FILETIME of sample stamp zero (when sampling
    started) and the sample rate. However, because the sample rate cannot be
    represented with full precision the accuracy of the FILETIME calculation is
    affected.

    To compensate for the lack of accuracy, the synchronization file maintains
    a sample stamp-to-computer time (called, MasterTime) mapping. Interpolation
    is then used to calculate a FILETIME given a sample stamp (and vise-versa).

    The attributes, sampleStamp and sampleTime, are used to predict (using
    interpolation) the FILETIME based upon a given sample stamp (and
    vise-versa). Currently, the only use for this conversion process is to
    enable correlation of EEG (sample_stamp) data with other sources of data
    such as Video (which works in FILETIME).

    """
    with open(snc_file, 'r') as f:
        f.seek(0, SEEK_END)
        endfile = f.tell()
        f.seek(352)  # end of header

        sampleStamp = []
        sampleTime = []
        while True:
            sampleStamp.append(unpack('i', f.read(4))[0])
            sampleTime.append(_filetime_to_dt(unpack('l', f.read(8))[0]))
            if f.tell() == endfile:
                break
        return sampleStamp, sampleTime


def _read_stc(stc_file):
    """Read Segment Table of Contents file.

    Returns
    -------
    hdr : dict
        - next_segment : Sample frequency in Hertz
        - final : Number of channels stored
        - padding : Padding

    all_stamp : list of dict
        - segment_name : Name of ERD / ETC file segment
        - start_stamp : First sample stamp that is found in the ERD / ETC pair
        - end_stamp : Last sample stamp that is still found in the ERD / ETC
        pair
        - sample_num : Number of samples recorded to the point that corresponds
        to start_stamp. This number accumulates over ERD / ETC pairs and is
        equal to sample_num of the first entry in the ETC file referenced by
        this STC entry


    Notes
    -----
    The Segment Table of Contents file is an index into pairs of (raw data file
    / table of contents file). It is used for mapping samples file segments.
    EEG raw data is split into segments in order to break a single file size
    limit (used to be 2GB) while still allowing quick searches. This file ends
    in the extension '.stc'. Default segment size (size of ERD file after which
    it is closed and new [ERD / ETC] pair is opened) is 50MB. The file starts
    with a generic EEG file header, and is followed by a series of fixed length
    records called the STC entries. ERD segments are named according to the
    following schema:
    <FIRST_NAME>, <LAST_NAME>_<GUID>.ERD (first)
    <FIRST_NAME>, <LAST_NAME>_<GUID>.ETC (first)
    <FIRST_NAME>, <LAST_NAME>_<GUID>_<INDEX>.ERD (second and subsequent files)
    <FIRST_NAME>, <LAST_NAME>_<GUID>_<INDEX>.ETC (second and subsequent files)

    <INDEX> is formatted with "%03d" format specifier and starts at 1 (initial
    value being 0 and omitted for compatibility with the previous versions).

    """
    with open(stc_file, 'r') as f:
        f.seek(0, SEEK_END)
        endfile = f.tell()
        f.seek(352)  # end of header
        hdr = {}
        hdr['next_segment'] = unpack('i', f.read(4))[0]
        hdr['final'] = unpack('i', f.read(4))[0]
        hdr['padding'] = unpack('i' * 12, f.read(48))

        all_stamp = []

        while True:
            if f.tell() == endfile:
                break
            stamp = {}
            stamp['segment_name'] = _make_str(unpack('c' * 256, f.read(256)))
            stamp['start_stamp'] = unpack('i', f.read(4))[0]
            stamp['end_stamp'] = unpack('i', f.read(4))[0]
            stamp['sample_num'] = unpack('i', f.read(4))[0]
            stamp['sample_span'] = unpack('i', f.read(4))[0]

            all_stamp.append(stamp)

    return hdr, all_stamp


def _read_hdr_file(ktlx_file):
    """Reads header of one KTLX file.

    Parameters
    ----------
    ktlx_file : str
        name of one of the ktlx files inside the directory (absolute path)

    Returns
    -------
    dict
        dict with information about the file

    """

    with open(ktlx_file, 'rb') as f:

        hdr = {}
        assert f.tell() == 0

        hdr['file_guid'] = hexlify(f.read(16))  # GUID, BUT little/big endian problems somewhere
        hdr['file_schema'], = unpack('H', f.read(2))
        assert hdr['file_schema'] in (7, 8, 9)

        hdr['base_schema'], = unpack('H', f.read(2))
        assert hdr['base_schema'] == 1  # p.3: base_schema 0 is rare, I think

        hdr['creation_time'] = datetime.fromtimestamp(
                                unpack('i', f.read(4))[0])
        hdr['patient_id'], = unpack('i', f.read(4))  # p.3: says long, but python-long requires 8 bytes
        hdr['study_id'], = unpack('i', f.read(4))  # p.3: says long, but python-long requires 8 bytes
        hdr['pat_last_name'] = _make_str(unpack('c' * 80, f.read(80)))
        hdr['pat_first_name'] = _make_str(unpack('c' * 80, f.read(80)))
        hdr['pat_middle_name'] = _make_str(unpack('c' * 80, f.read(80)))
        hdr['patient_id'] = _make_str(unpack('c' * 80, f.read(80)))
        assert f.tell() == 352

        if hdr['file_schema'] >= 7:
            hdr['sample_freq'], = unpack('d', f.read(8))
            hdr['num_channels'], = unpack('i', f.read(4))
            hdr['deltabits'], = unpack('i', f.read(4))
            hdr['phys_chan'] = unpack('i' * hdr['num_channels'],
                                 f.read(hdr['num_channels'] * 4))

            f.seek(4464)
            hdr['headbox_type'] = unpack('i' * 4, f.read(16))
            hdr['headbox_sn'] = unpack('i' * 4, f.read(16))
            hdr['headbox_sw_version'] = _make_str(unpack('c' * 40, f.read(40)))
            hdr['dsp_hw_version'] = _make_str(unpack('c' * 10, f.read(10)))
            hdr['dsp_sw_version'] = _make_str(unpack('c' * 10, f.read(10)))
            hdr['discardbits'], = unpack('i', f.read(4))

        if hdr['file_schema'] >= 8:
            hdr['shorted'] = unpack('h' * 1024, f.read(2048))
            hdr['frequency_factor'] = unpack('h' * 1024, f.read(2048))

    return hdr


class Ktlx():
    def __init__(self, ktlx_dir):
        if isinstance(Ktlx_dir, str):
            self.ktlx_dir = ktlx_dir
            self._read_hdr_dir()

    def _read_hdr_dir(self):
        """Read the header for basic information.

        Especially, it's useful to have the sampling frequency

        """
        erd_file = join(self.ktlx_dir, basename(self.ktlx_dir) + '.erd')
        if exists(erd_file):
            self._basename = splitext(basename(self.ktlx_dir))[0]
        else:  # if the folder was renamed
            erd_files = glob(join(self.ktlx_dir, '*.erd'))
            # search for the one ERD file that doesn't end in _xxx.erd
            erd_file = [x for x in erd_files
                        if not match('_[0-9]{3}.erd', x[-8:])]
            if len(erd_file) == 1:
                self._basename = splitext(basename(erd_file[0]))[0]
            else:
                raise IOError('could not find one erd file. Found: ' +
                              '\n'.join(erd_file))

        self._orig = _read_hdr_file(join(self.ktlx_dir,
                                         self._basename + '.erd'))

    def return_dat(self, chan, begsam, endsam):
        """TODO: prepare functions
        1. read stc for the content of the folder
        2. loop over erd and concatenate them

        it should allow for random access to the files, otherwise it's too slow
        to read the complete recording.

        """
        pass

    def return_hdr(self):
        """
        Returns the header for further use.

        Returns
        -------
        subj_id : str
            subject identification code
        start_time : datetime
            start time of the dataset
        s_freq : float
            sampling frequency
        chan_name : list of str
            list of all the channels
        n_samples : int
            number of samples in the dataset
        orig : dict
            additional information taken directly from the header

        """

        orig = self._orig
        if orig['patient_id']:
            subj_id = orig['patient_id']
        else:
            subj_id = (orig['pat_first_name'] + orig['pat_middle_name'] +
            orig['pat_last_name'])

        start_time = orig['creation_time']
        s_freq = orig['sample_freq']
        chan_name = ['']  # TODO
        n_samples = 0  # TODO

        try:
            orig['notes'] = self._read_notes()
        except IOError:
            orig['notes'] = 'could not find .ent file'
        return subj_id, start_time, s_freq, chan_name, n_samples, orig

    def _read_notes(self):
        """Reads the notes of the Ktlx recordings.

        However, this function formats the note already in the EDFBrowser
        format. Maybe the format should be more general.
        """
        ent_file = join(self.ktlx_dir, self._basename + '.ent')

        ent_notes = _read_ent(ent_file)
        allnote = []
        for n in ent_notes:
            allnote.append(n['value'])

        s_freq = self._orig['sample_freq']
        start_time = self._orig['creation_time']
        pcname = '0CFEBE72-DA20-4b3a-A8AC-CDD41BFE2F0D'
        note_time = []
        note_name = []
        note_note = []
        for n in allnote:
            if n['Text'] == 'Analyzed Data Note':  # seems some automatic message
                continue
            if not n['Text']:
                continue
            if 'User' not in n['Data'].keys():
                continue
            user1 = n['Data']['User'] == 'Persyst'
            user2 = n['Data']['User'] == 'eeg'
            user3 = n['Data']['User'] == pcname
            user4 = n['Data']['User'] == 'XLSpike - Intracranial'
            user5 = n['Data']['User'] == 'XLEvent - Intracranial'
            if user1 or user2 or user3 or user4 or user5:
                continue
            if len(n['Data']['User']) == 0:
                note_name.append('-unknown-')
            else:
                note_name.append(n['Data']['User'].split()[0])
            note_time.append(start_time +
                            timedelta(seconds=n['Stamp'] / s_freq))
            note_note.append(n['Text'])

        s = []
        for time, name, note in zip(note_time, note_name, note_note):
            s.append(datetime.strftime(time, '%Y-%m-%dT%H:%M:%S') +
            ',' + '0' + ',' +  # zero duration
            note + ' (' + name + ')')

        return '\n'.join(s)


if __name__ == "__main__":
    filename = '/home/gio/smb4k/MAD.RESEARCH.PARTNERS.ORG/cashlab/lab_files/Original Data/MG/MG55/MG55_Raw_Xltek/Xxxxxxxxxxx~ X_90d439a0-6217-4045-a325-0836fe1c11a2/Xxxxxxxxxxx~ X_90d439a0-6217-4045-a325-0836fe1c11a2_070.erd'
    a = _read_erd(filename, 1)
